const LAYOUT_STORAGE_KEY = "centaur-layout-v1";

const layoutPrefs = loadLayoutPrefs();

function isLowPowerClient() {
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const narrow = window.matchMedia("(max-width: 900px)").matches;
  const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return coarse || narrow || iOS;
}

function initAmbientCanvas() {
  const canvas = document.getElementById("ambientCanvas");
  const ctx = canvas?.getContext("2d", { alpha: true });
  if (!canvas || !ctx) return;

  // Safari iOS repeatedly crashes under full-screen animated canvases + large JSON.
  // Keep a static wash on phones/tablets; animate only on desktop.
  const lowPower = isLowPowerClient();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (lowPower || reducedMotion.matches) {
    canvas.width = 1;
    canvas.height = 1;
    canvas.style.display = "none";
    document.body.classList.add("ambient-static");
    return;
  }

  let width = 0;
  let height = 0;
  let particles = [];
  let frameId = 0;
  let pointerX = 0.76;
  let pointerY = 0.34;
  let pointerActive = false;
  let lastPaint = 0;

  const seedParticles = () => {
    const count = Math.min(36, Math.max(16, Math.round((width * height) / 28000)));
    particles = Array.from({ length: count }, (_, index) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.09,
      vy: (Math.random() - 0.5) * 0.06,
      radius: index % 9 === 0 ? 1.5 : 0.7 + Math.random() * 0.7,
      phase: Math.random() * Math.PI * 2,
    }));
  };

  const paint = time => {
    if (!canvas.isConnected || document.hidden) return;
    // Cap ~30fps to cut Safari/GPU load.
    if (time - lastPaint < 32) {
      frameId = requestAnimationFrame(paint);
      return;
    }
    lastPaint = time;
    ctx.clearRect(0, 0, width, height);

    const focusX = pointerX * width;
    const focusY = pointerY * height;
    const glow = ctx.createRadialGradient(focusX, focusY, 0, focusX, focusY, Math.max(width, height) * 0.42);
    glow.addColorStop(0, pointerActive ? "rgba(47, 111, 203, .08)" : "rgba(47, 111, 203, .05)");
    glow.addColorStop(1, "rgba(47, 111, 203, 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, width, height);

    particles.forEach(particle => {
      particle.x += particle.vx;
      particle.y += particle.vy;
      if (particle.x < -8) particle.x = width + 8;
      if (particle.x > width + 8) particle.x = -8;
      if (particle.y < -8) particle.y = height + 8;
      if (particle.y > height + 8) particle.y = -8;
    });

    // Skip O(n²) connection lines — they were the main mobile crash driver.
    particles.forEach(particle => {
      const pulse = 0.72 + Math.sin(time * 0.001 + particle.phase) * 0.24;
      ctx.fillStyle = `rgba(47, 111, 203, ${pulse * 0.65})`;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
      ctx.fill();
    });

    frameId = requestAnimationFrame(paint);
  };

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = Math.max(1, Math.round(window.innerWidth));
    height = Math.max(1, Math.round(window.innerHeight));
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    seedParticles();
  };

  window.addEventListener("pointermove", event => {
    pointerX = event.clientX / Math.max(width, 1);
    pointerY = event.clientY / Math.max(height, 1);
    pointerActive = true;
  }, { passive: true });
  window.addEventListener("blur", () => { pointerActive = false; });

  window.addEventListener("resize", resize, { passive: true });
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(frameId);
    if (!document.hidden) frameId = requestAnimationFrame(paint);
  });

  resize();
  frameId = requestAnimationFrame(paint);
}

function loadLayoutPrefs() {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return { header: "auto", autoShrink: true, folds: {} };
    const parsed = JSON.parse(raw);
    return {
      header: parsed.header || "auto",
      autoShrink: parsed.autoShrink !== false,
      folds: parsed.folds || {},
    };
  } catch {
    return { header: "auto", autoShrink: true, folds: {} };
  }
}

function saveLayoutPrefs() {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layoutPrefs));
  } catch {
    /* ignore quota errors */
  }
}

function effectiveHeaderMode() {
  return state.tab === "project" ? "expanded" : "compact";
}

function applyHeaderLayout() {
  const topbar = document.getElementById("topbar");
  if (!topbar) return;
  const mode = effectiveHeaderMode();
  topbar.classList.toggle("header-expanded", mode === "expanded");
  topbar.classList.toggle("header-compact", mode === "compact");
  topbar.classList.toggle("header-focus", mode === "focus");
  const expandBtn = document.getElementById("headerExpandBtn");
  const compactBtn = document.getElementById("headerCompactBtn");
  const focusBtn = document.getElementById("headerFocusBtn");
  const autoBtn = document.getElementById("headerAutoBtn");
  if (expandBtn) expandBtn.setAttribute("aria-pressed", mode === "expanded" ? "true" : "false");
  if (compactBtn) compactBtn.setAttribute("aria-pressed", mode === "compact" ? "true" : "false");
  if (focusBtn) focusBtn.setAttribute("aria-pressed", mode === "focus" ? "true" : "false");
  if (autoBtn) autoBtn.setAttribute("aria-pressed", layoutPrefs.header === "auto" && layoutPrefs.autoShrink ? "true" : "false");
  if (expandBtn) expandBtn.textContent = mode === "focus" ? "Exit focus" : "Expand";
}

function restoreFoldStates() {
  document.querySelectorAll("details.fold-block[data-fold-id]").forEach(el => {
    const id = el.dataset.foldId;
    if (id in layoutPrefs.folds) el.open = !!layoutPrefs.folds[id];
    el.addEventListener("toggle", () => {
      layoutPrefs.folds[id] = el.open;
      saveLayoutPrefs();
    });
  });
}

function bindLayoutControls() {
  const setHeader = mode => {
    layoutPrefs.header = mode;
    if (mode === "auto") layoutPrefs.autoShrink = true;
    saveLayoutPrefs();
    applyHeaderLayout();
  };
  document.getElementById("headerExpandBtn")?.addEventListener("click", () => setHeader("expanded"));
  document.getElementById("headerCompactBtn")?.addEventListener("click", () => setHeader("compact"));
  document.getElementById("headerFocusBtn")?.addEventListener("click", () => setHeader("focus"));
  document.getElementById("headerAutoBtn")?.addEventListener("click", () => {
    layoutPrefs.header = "auto";
    layoutPrefs.autoShrink = true;
    saveLayoutPrefs();
    applyHeaderLayout();
  });
  restoreFoldStates();
  applyHeaderLayout();
}

const state = {
  data: null,
  qualLoaded: false,
  qualLoading: false,
  tab: "project",
  runId: null,
  modelSet: "all",
  task: "tax_prep",
  mode: "augmentation",
  selectedModel: null,
  textTab: "output",
  rubricFocus: null,
  overviewTask: "counselling",
  compareTeaserPair: 0,
  /** Scoreboard-only judge filter — independent of Single-run Result / Qualitative. */
  rankings: {
    judgeFilter: "aggregate",
  },
  /** Single-run Result judge filter — never share with Scoreboard or Qualitative. */
  heatmaps: {
    judgeFilter: "aggregate",
  },
  /** Qualitative pairwise rationales — independent of Heatmaps / Scoreboard judge filters. */
  qual: {
    judgeFilter: null,
    pairModel: null,
  },
  compare: {
    task: "tax_prep",
    mode: "augmentation",
    runId: null,
    modelA: null,
    modelB: null,
    rubricView: "pair",
    rubricJudge: "average",
    paneA: "output",
    paneB: "output",
    radarShowA: true,
    radarShowB: true,
  },
};

/** Paper Table / Figure 2 provenance (GDPval vs Anthropic Economic Index vs designed). */
const taskSourceHints = {
  counselling: "Anthropic Economic Index",
  meal_plan: "GDPval",
  market_trends: "GDPval",
  operations_research: "Anthropic Economic Index",
  tax_prep: "Designed task",
  travel_planning: "GDPval",
  tutoring: "Anthropic Economic Index",
};

const taskSourceUrls = {
  GDPval: "https://openai.com/index/gdpval/",
  "Anthropic Economic Index": "https://www.anthropic.com/economic-index",
};

const taskTaglines = {
  counselling: "Planning a counseling session",
  market_trends: "Analyzing U.S. Energy Market",
  meal_plan: "Creating daily 7-day meal",
  operations_research: "Drafting OR internal report for executives",
  tax_prep: "Spotting Tax filing discrepancies",
  travel_planning: "Crafting Tokyo trip itinerary",
  tutoring: "Planning a math lesson.",
};

const taskTypeTone = {
  "Professional / analytical": "analytical",
  "Structured planning": "planning",
  "Human-facing interactive": "interactive",
};

function taskTypeClass(type) {
  return taskTypeTone[type] || "default";
}

function taskTagline(slug) {
  return taskTaglines[slug] || "";
}

function taskSourceBadgesHtml(slug) {
  const label = taskSourceLabel(slug);
  const badges = [];
  const cache = "20260717t";
  if (label === "GDPval") {
    badges.push(`<a class="task-source-badge" href="${esc(taskSourceUrls.GDPval)}" target="_blank" rel="noopener noreferrer" title="OpenAI GDPval"><img class="task-source-logo openai" src="assets/openai-logo.png?v=${cache}" alt="" width="18" height="18" /><span>GDPval</span></a>`);
  } else if (label === "Anthropic Economic Index") {
    badges.push(`<a class="task-source-badge" href="${esc(taskSourceUrls["Anthropic Economic Index"])}" target="_blank" rel="noopener noreferrer" title="Anthropic Economic Index"><img class="task-source-logo anthropic" src="assets/anthropic-logo.png?v=${cache}" alt="" width="18" height="18" /><span>Anthropic Economic Index</span></a>`);
  } else if (/designed/i.test(label)) {
    badges.push(`<span class="task-source-badge task-source-badge-plain"><span>Designed task</span></span>`);
  } else {
    badges.push(`<span class="task-source-badge task-source-badge-plain"><span>${esc(label)}</span></span>`);
  }
  return badges.join("");
}

/** Overview Compare teaser presets — real task × regime × model pairs. */
const compareTeaserPairs = [
  {
    label: "Counseling · GPT-4.1 vs DeepSeek",
    task: "counselling",
    mode: "augmentation",
    modelA: "GPT-4.1",
    modelB: "DeepSeek-V3.1",
    paneA: "scaffold",
    paneB: "scaffold",
  },
  {
    label: "Menu Planning · GPT-5-Mini vs plain",
    task: "meal_plan",
    mode: "augmentation",
    modelA: "GPT-5-Mini",
    modelB: "plain",
    paneA: "scaffold",
    paneB: "output",
  },
  {
    label: "Tax Prep · GPT-4.1 vs plain",
    task: "tax_prep",
    mode: "augmentation",
    modelA: "GPT-4.1",
    modelB: "plain",
    paneA: "scaffold",
    paneB: "output",
  },
];

const glossary = {
  automation: "The model completes the task end-to-end on its own and produces the deliverable.",
  augmentation: "The model writes assistance text for a fixed GPT-3.5-Turbo worker, which then produces the deliverable.",
  "assistance text": "Process-only guidance — such as plans, checklists, and self-review steps — written by the assistant model for the worker model. It does not contain a direct answer to the task.",
  "worker model": "The model that produces the final task output. In augmentation this is always GPT-3.5-Turbo; in automation it is the model under test.",
  "assistant model": "The focal model under test in augmentation. It writes assistance text for the worker rather than the task deliverable.",
  "pairwise comparison": "Judges see two anonymized outputs side-by-side, pick a winner, and score rubric dimensions — never knowing which model produced which.",
  "win rate": "Share of pairwise matchups a model wins within a task and regime. Higher is better.",
  "rank-of-ranks": "Per-task rank (1 = best) averaged across tasks in the selected model set. Lower is better.",
  "model pool": "Which models are eligible for ranking: All candidates (includes the plain unaided worker baseline) vs Assistants only (focal assistant models).",
  "rank universe": "Synonym for model pool — which models are eligible for ranking.",
  "leave-family-out": "A judge never scores outputs from its own model family (e.g., Claude does not judge Claude outputs), reducing same-family preference.",
  "role-swap": "Compares a model's automation performance (solves the task alone) versus augmentation performance (helps a fixed worker). Axes use reverse rank (inverted mean rank so higher = better).",
  "standard error": "Uncertainty across 10 independent replications (SE = SD / √10). Smaller means a more stable ranking.",
  "baseline (plain worker)": "An augmentation run in which GPT-3.5-Turbo receives no assistance text. This shows what the fixed worker model achieves unaided.",
  "replication run": "One full independent pass of generation, worker execution, and judging. The dashboard aggregates ten runs for paper-level results.",
  "judge panel": "Four LLM judges (GPT-4.1, Claude-Opus-4.8, DeepSeek-V3.1, Gemini-3.1-Pro). Aggregate combines all eligible judges per cell.",
  rubric: "Task-specific scoring dimensions (e.g., empathy, accuracy) plus five general dimensions applied to every task.",
};

const qualTabDescriptions = {
  output: "The worker's final deliverable for this task–model cell.",
  scaffold: "Assistance text written by the assistant model for the worker model (augmentation only).",
  scaffoldPrompt: "The prompt used to generate the assistance text, together with the instructions given to the worker model.",
  prompt: "The shared task prompt, augmentation specs, and judge rubric for this task.",
};


function renderQualQuickPicks(ranked) {
  const el = document.getElementById("qualQuickPicks");
  if (!el) return;
  const top = ranked.slice().sort((a, b) => a.display_rank - b.display_rank).slice(0, 3);
  if (!top.length) {
    el.innerHTML = `<div class="qual-empty-state">No ranked models for ${esc(cleanTaskTitle(state.task))} · ${esc(modeLabels[state.mode])}. Try another task or usage regime.</div>`;
    return;
  }
  el.innerHTML = `<span class="qual-quick-label">Top ranked:</span>${top.map(d => `<button type="button" class="qual-quick-chip ${state.selectedModel === d.model_label ? "active" : ""}" data-quickmodel="${esc(d.model_label)}"><span class="rank-badge ${Number(d.display_rank) <= 3 ? "top" : ""}">${d.display_rank}</span>${esc(displayModel(d.model_label, state.mode))}</button>`).join("")}`;
  el.querySelectorAll("[data-quickmodel]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.selectedModel = btn.dataset.quickmodel;
      renderAll();
    });
  });
}

const controlsByTab = {
  project: [],
  compare: [],
  replicates: [],
  overview: ["run"],
  rankings: ["run", "task", "mode"],
  judges: ["modelSet", "task", "mode"],
  qualitative: ["run", "task", "mode"],
  validation: ["task"],
};

const taskOrder = ["counselling", "market_trends", "meal_plan", "operations_research", "tax_prep", "travel_planning", "tutoring"];
const taskLabels = {
  counselling: "Counseling",
  market_trends: "Market Trends",
  meal_plan: "Menu Planning",
  operations_research: "Operations Research",
  tax_prep: "Tax Prep",
  travel_planning: "Travel Agent",
  tutoring: "Tutoring",
};
const modeLabels = { augmentation: "Augmentation", automation: "Automation" };
const judgeLabels = {
  aggregate: "Aggregate",
  "gpt-4.1": "GPT-4.1",
  "anthropic/claude-opus-4-8": "Claude-Opus-4.8",
  "deepseek-ai/DeepSeek-V3.1": "DeepSeek-V3.1",
  "google/gemini-3.1-pro": "Gemini-3.1-Pro",
};
function canonicalJudge(name) {
  if (!name) return "";
  const s = String(name).toLowerCase();
  if (s.includes("claude") || s.includes("opus") || s.includes("anthropic")) return "claude";
  if (s.includes("deepseek")) return "deepseek";
  if (s.includes("gemini") || s.includes("google")) return "gemini";
  if (s.includes("gpt") || s.includes("openai") || s.includes("o3") || s.includes("o4")) return "gpt41";
  return s;
}

const canonicalJudgeLabels = {
  claude: "Claude-Opus-4.8",
  deepseek: "DeepSeek-V3.1",
  gemini: "Gemini-3.1-Pro",
  gpt41: "GPT-4.1",
};

function judgeDisplay(name) {
  return judgeLabels[name] || canonicalJudgeLabels[canonicalJudge(name)] || name;
}

const modelShort = {
  "GPT-5-Mini": "G5M",
  "GPT-4.1": "G4.1",
  "GPT-O4-Mini": "O4",
  "GPT-O3-Mini": "O3",
  "GPT-OSS-120B": "OSS",
  "DeepSeek-V3.1": "DS",
  "Claude-Opus-4.8": "Opus",
  "Claude-Sonnet-4.6": "Sonnet",
  "Gemini-3.1-Pro": "Gemini",
  "plain": "Plain",
  "GPT-3.5-Turbo": "3.5",
};
const validationChecks = [
  {
    id: "gpt_ladder_claude",
    title: "GPT-family automation ladder judged by Claude",
    judge: "anthropic/claude-opus-4-8",
    family: "GPT family",
    models: ["GPT-3.5-Turbo", "GPT-O3-Mini", "GPT-O4-Mini", "GPT-4.1", "GPT-5-Mini"],
    expectedBest: "GPT-5-Mini",
    note: "GPT-OSS-120B is omitted because it is an open-weight reference model rather than a clean generation step. Treat the GPT-family ordering as a reference capability gradient, not a perfectly chronological release ladder.",
  },
  {
    id: "claude_pair_gpt",
    title: "Claude-family automation pair judged by GPT-4.1",
    judge: "gpt-4.1",
    family: "Claude family",
    models: ["Claude-Sonnet-4.6", "Claude-Opus-4.8"],
    expectedBest: "Claude-Opus-4.8",
    note: "This is a two-model sanity check rather than a full generation ladder.",
  },
];
const rubricLabels = {
  counselling: {
    task_dimension_1: "Empathy and therapeutic tone",
    task_dimension_2: "Pattern recognition without overdiagnosis",
    task_dimension_3: "Evidence-informed psychological framing",
    task_dimension_4: "Actionable coping and goal-setting",
    task_dimension_5: "Ethical boundaries and escalation",
    task_dimension_6: "Coherence, warmth, and usefulness",
  },
  market_trends: {
    task_dimension_1: "Trend identification",
    task_dimension_2: "Economic mechanism quality",
    task_dimension_3: "Coverage of market drivers",
    task_dimension_4: "Analytical balance and nuance",
    task_dimension_5: "Client usefulness and actionability",
    task_dimension_6: "Conclusion quality",
  },
  meal_plan: {
    task_dimension_1: "Dietary safety",
    task_dimension_2: "Preference fit",
    task_dimension_3: "Affordability",
    task_dimension_4: "Nutritional adequacy and variety",
    task_dimension_5: "Simplicity and usability",
    task_dimension_6: "Completeness",
  },
  operations_research: {
    task_dimension_1: "Data and validation",
    task_dimension_2: "Analytical framework",
    task_dimension_3: "Recommendations",
    task_dimension_4: "Trade-offs and risks",
    task_dimension_5: "KPIs and communication",
    task_dimension_6: "Executive memo quality",
  },
  tax_prep: {
    task_dimension_1: "Rule accuracy",
    task_dimension_2: "Error detection",
    task_dimension_3: "Calculation quality",
    task_dimension_4: "Form guidance",
    task_dimension_5: "Dependent analysis",
    task_dimension_6: "Clear communication",
  },
  travel_planning: {
    task_dimension_1: "Completeness",
    task_dimension_2: "Cost realism and arithmetic",
    task_dimension_3: "Hotel and transport practicality",
    task_dimension_4: "Itinerary quality",
    task_dimension_5: "Travel-agent professionalism",
    task_dimension_6: "Handling uncertainty",
  },
  tutoring: {
    task_dimension_1: "Mathematical correctness",
    task_dimension_2: "Age-appropriate explanation and pacing",
    task_dimension_3: "Analogy quality",
    task_dimension_4: "Misconception handling",
    task_dimension_5: "Classroom practicality and engagement",
    task_dimension_6: "Assessment/checks for understanding",
  },
};
const rubricDetails = {
  counselling: {
    task_dimension_1: "How well the response validates the client's feelings, uses supportive language, and avoids minimizing distress.",
    task_dimension_2: "Whether it cautiously identifies possible patterns such as burnout, perfectionism, avoidance, low self-efficacy, or value mismatch without diagnosing.",
    task_dimension_3: "Whether it uses CBT, motivational interviewing, or positive psychology accurately and in plain language.",
    task_dimension_4: "Whether it gives concrete next steps for regulation, reframing, values clarification, and near-term goals.",
    task_dimension_5: "Whether it includes appropriate limits and encourages professional support if distress is severe or persistent.",
    task_dimension_6: "Whether the full single-session response is coherent, warm, useful, and appropriately bounded.",
  },
  market_trends: {
    task_dimension_1: "Exactly three bullish and exactly three bearish trends, clearly categorized.",
    task_dimension_2: "Causal mechanisms linking each trend to natural-gas prices through supply, demand, storage, LNG, infrastructure, policy, or expectations.",
    task_dimension_3: "Meaningful coverage of supply, demand, weather, and policy/regulation, including interactions among them.",
    task_dimension_4: "Nuance around uncertainty, competing forces, conditional scenarios, weather variability, production response, and policy/geopolitical risk.",
    task_dimension_5: "Usefulness to investors or energy firms through implications for risk management, timing, hedging, capacity, or strategy.",
    task_dimension_6: "A clear 2-3 sentence synthesis of the overall client-facing outlook.",
  },
  meal_plan: {
    task_dimension_1: "Strictly avoids shellfish, gluten, lactose-containing dairy, and onion.",
    task_dimension_2: "Fits meat, potatoes, Mexican, Thai, and Indian flavor preferences while avoiding very salty/sweet foods and strong seasoning.",
    task_dimension_3: "Uses affordable, common grocery-store ingredients.",
    task_dimension_4: "Provides variety and adequate proteins, carbs, fats, vegetables, fruits, and micronutrient coverage.",
    task_dimension_5: "Easy to follow, clearly structured, simple enough for the target user.",
    task_dimension_6: "Includes breakfast, lunch, dinner, snacks for all seven days, grocery list, and prep notes.",
  },
  operations_research: {
    task_dimension_1: "Identifies route, demand, fleet, warehouse, service, and cost data plus collection and validation methods.",
    task_dimension_2: "Uses suitable OR methods such as MILP, simulation, scenario analysis, routing, or allocation optimization.",
    task_dimension_3: "At least two feasible practical solutions with clear lines of action.",
    task_dimension_4: "Explicit cost, service, resource, implementation, and risk trade-offs.",
    task_dimension_5: "Clear KPIs and executive communication plan for both technical and non-technical audiences.",
    task_dimension_6: "Concise, self-contained 300-400 word executive memo with appropriate tone and structure.",
  },
  tax_prep: {
    task_dimension_1: "Correct federal and California tax rules for self-employment income, dependent rules, mortgage interest, deductions, and state/federal differences.",
    task_dimension_2: "Detects the known filing mistakes, including income mismatch, missing schedules, deduction errors, dependent-credit issues, and CA inconsistencies.",
    task_dimension_3: "Provides income, AGI, deductions, taxable income, self-employment tax, or tax-estimate calculations where possible.",
    task_dimension_4: "Gives clear guidance on Schedule C, Schedule SE, Schedule A vs. standard deduction, Form 1040, and California corrections.",
    task_dimension_5: "Handles the 22-year-old full-time student with $18k income cautiously and correctly.",
    task_dimension_6: "Explains dense tax rules in plain English so the client understands what changes and why.",
  },
  travel_planning: {
    task_dimension_1: "Covers clarifying questions, costs, hotels, transport, customs/regulations, itinerary, package logic, and budget confirmation.",
    task_dimension_2: "Flight, lodging, transport, food/activity estimates are plausible and correctly summed without exceeding budget.",
    task_dimension_3: "Provides viable hotel options, airport/transit guidance, and practical rail/pass advice.",
    task_dimension_4: "Five days of morning/afternoon/evening plans that are geographically sensible and fatigue-aware.",
    task_dimension_5: "Clear, customer-focused, travel-agent style with appropriate caveats around estimates.",
    task_dimension_6: "Asks clarifying questions for missing info while still providing a useful provisional plan.",
  },
  tutoring: {
    task_dimension_1: "Mathematically accurate treatment of improper fractions and mixed numbers with no concept/example errors.",
    task_dimension_2: "Clear Grade 3 pacing and language, avoiding abstract notation without visual support.",
    task_dimension_3: "Analogy is concrete and understandable for 8-year-olds.",
    task_dimension_4: "Identifies and corrects common misconceptions, ideally with a memorable check or trick.",
    task_dimension_5: "Immediately usable classroom segment with overt student participation and engagement.",
    task_dimension_6: "Specific formative checks such as thumbs, exit ticket, visual problem, or think-pair-share.",
  },
};
const generalRubricLabels = {
  general_instruction_following: "General: instruction following",
  general_accuracy_specificity: "General: accuracy and specificity",
  general_practical_usefulness: "General: practical usefulness",
  general_organization_readability: "General: organization and readability",
  general_tone_audience_fit: "General: tone and audience fit",
};
const generalRubricDetails = {
  general_instruction_following: "Satisfies explicit requirements and constraints in the task prompt.",
  general_accuracy_specificity: "Avoids false claims, vague filler, and unsupported assumptions.",
  general_practical_usefulness: "Gives concrete, usable guidance or outputs.",
  general_organization_readability: "Clear structure, easy to scan, appropriate formatting.",
  general_tone_audience_fit: "Matches the role, user need, and professional context.",
};

function runStats(runId = state.runId) {
  return state.data?.meta?.run_stats?.[runId] || null;
}

function totalRunStats() {
  const stats = state.data?.meta?.run_stats || {};
  return Object.values(stats).reduce(
    (acc, s) => ({
      outputs: acc.outputs + (s.outputs || 0),
      judgments: acc.judgments + (s.unique_judgments || s.judgments || 0),
    }),
    { outputs: 0, judgments: 0 },
  );
}

function mergeQualitativeData(qual) {
  if (!qual?.runs_by_id || !state.data?.runs_by_id) return;
  for (const [runId, qualBundle] of Object.entries(qual.runs_by_id)) {
    const target = state.data.runs_by_id[runId];
    if (!target) continue;
    if (!target.runs) target.runs = {};
    for (const [key, qualRun] of Object.entries(qualBundle.runs || {})) {
      const cell = target.runs[key] || (target.runs[key] = {
        task: qualRun.task,
        task_label: qualRun.task_label,
        mode: qualRun.mode,
      });
      cell.outputs = qualRun.outputs || [];
      cell.judgments = qualRun.judgments || [];
    }
  }
  syncActiveRunMirror();
  state.qualLoaded = true;
}

function syncActiveRunMirror() {
  const bundle = activeData();
  if (bundle?.runs) state.data.runs = bundle.runs;
}

function setQualLoading(on) {
  state.qualLoading = on;
  document.body.classList.toggle("qual-loading", on);
  const note = document.getElementById("qualLoadingNote");
  if (note) note.classList.toggle("hidden", !on);
}

let qualLoadPromise = null;
function ensureQualitativeData() {
  if (state.qualLoaded) return Promise.resolve();
  if (qualLoadPromise) return qualLoadPromise;
  const qualFile = state.data?.meta?.data_files?.qualitative || "dashboard-qualitative.json";
  setQualLoading(true);
  qualLoadPromise = fetch(qualFile)
    .then(r => {
      if (!r.ok) throw new Error(`Failed to load ${qualFile} (${r.status})`);
      return r.json();
    })
    .then(data => {
      mergeQualitativeData(data);
      setQualLoading(false);
      renderRankings();
      renderQualitative();
      renderCompare();
      renderOverviewCompareTeaser();
      applyTermTooltips(document.getElementById("qualitative"));
      applyTermTooltips(document.getElementById("compare"));
      applyTermTooltips(document.getElementById("rankings"));
      applyTermTooltips(document.getElementById("overviewCompareTeaser"));
    })
    .catch(err => {
      setQualLoading(false);
      qualLoadPromise = null;
      const el = document.getElementById("qualText");
      if (el) el.innerHTML = `<div class="qual-empty-state">Qualitative bundle failed to load: ${esc(String(err))}</div>`;
      throw err;
    });
  return qualLoadPromise;
}

function needsQualitativeData(tab = state.tab) {
  return tab === "qualitative" || tab === "rankings" || tab === "compare";
}

function qualDataReady() {
  const run = currentRun();
  return !!(run?.outputs?.length || run?.judgments?.length);
}

function runList() {
  return state.data?.meta?.replicate_runs || [{ id: state.data?.meta?.run_id, label: state.data?.meta?.run_id || "Run" }];
}

function activeData(runId = state.runId) {
  const id = runId || state.data?.meta?.default_run_id || state.data?.meta?.run_id;
  return state.data?.runs_by_id?.[id] || state.data;
}

function activeRunMeta(runId = state.runId) {
  const id = runId || state.data?.meta?.default_run_id || state.data?.meta?.run_id;
  return runList().find(r => r.id === id) || { id, label: id };
}

function modelAllowed(label) {
  const set = state.data.model_sets[state.modelSet];
  if (set.include) return set.include.includes(label);
  if (set.exclude) return !set.exclude.includes(label);
  return true;
}

function cleanTaskTitle(slug) {
  return taskLabels[slug] || slug;
}

function displayModel(label, mode = state.mode) {
  if (label === "gpt-3.5-turbo") return "GPT-3.5-Turbo";
  if (mode === "augmentation" && label === "plain") return "GPT-3.5-Turbo (plain)";
  return label || "";
}

function isOwnFamily(judge, modelLabel) {
  if (!judge || judge === "aggregate") return false;
  if (judge.startsWith("gpt-") || judge.includes("openai")) {
    return modelLabel === "plain" || modelLabel === "GPT-3.5-Turbo" || modelLabel.startsWith("GPT-");
  }
  if (judge.includes("claude") || judge.includes("anthropic")) {
    return modelLabel.startsWith("Claude-");
  }
  if (judge.includes("DeepSeek")) {
    return modelLabel.startsWith("DeepSeek");
  }
  if (judge.includes("gemini") || judge.includes("google")) {
    return modelLabel.startsWith("Gemini");
  }
  return false;
}

function visibleModels(mode, runId = state.runId) {
  return [...new Set(activeData(runId).aggregate
    .filter(d => d.mode === mode && modelAllowed(d.model_label))
    .map(d => d.model_label))];
}

function num(x) {
  return typeof x === "number" ? x : Number(x);
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function mdInline(escaped) {
  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_([^_\n]+)_(?=[\s.,;:)]|$)/g, "$1<em>$2</em>");
}

function mdToHtml(raw) {
  const lines = String(raw ?? "").replace(/\r\n/g, "\n").split("\n");
  let html = "";
  let para = [];
  let listType = null;
  const flushPara = () => {
    if (para.length) { html += `<p>${para.map(l => mdInline(esc(l))).join("<br>")}</p>`; para = []; }
  };
  const closeList = () => { if (listType) { html += `</${listType}>`; listType = null; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (/^```/.test(trimmed)) {
      flushPara(); closeList();
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
      html += `<pre class="md-code">${esc(buf.join("\n"))}</pre>`;
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushPara(); closeList();
      const lvl = heading[1].length;
      html += `<h${lvl} class="md-h md-h${lvl}">${mdInline(esc(heading[2]))}</h${lvl}>`;
      continue;
    }
    if (trimmed === "") { flushPara(); closeList(); continue; }
    const ul = trimmed.match(/^[-*•]\s+(.*)$/);
    if (ul) {
      flushPara();
      if (listType !== "ul") { closeList(); html += '<ul class="md-list">'; listType = "ul"; }
      html += `<li>${mdInline(esc(ul[1]))}</li>`;
      continue;
    }
    const ol = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
    if (ol) {
      flushPara();
      if (listType !== "ol") { closeList(); html += '<ol class="md-list">'; listType = "ol"; }
      html += `<li>${mdInline(esc(ol[2]))}</li>`;
      continue;
    }
    closeList();
    para.push(line);
  }
  flushPara(); closeList();
  return html || `<p>${mdInline(esc(String(raw ?? "")))}</p>`;
}

function renderQualSections(sections) {
  if (!sections.length) return "";
  return `<div class="qual-doc">${sections.map(s => {
    const sub = s.sublabel ? `<span class="qual-sec-sub">${esc(s.sublabel)}</span>` : "";
    const body = s.empty
      ? `<div class="qual-sec-body qual-empty">${esc(s.body)}</div>`
      : `<div class="qual-sec-body md">${mdToHtml(s.body)}</div>`;
    return `<section class="qual-section qual-${s.kind}">`
      + `<header class="qual-sec-head"><span class="qual-sec-label">${esc(s.label)}</span>${sub}</header>`
      + body + `</section>`;
  }).join("")}</div>`;
}

function rubricName(dim) {
  return rubricLabels[state.task]?.[dim] || generalRubricLabels[dim] || dim;
}

function rubricTip(dim) {
  return rubricDetails[state.task]?.[dim] || generalRubricDetails[dim] || rubricName(dim);
}

/** Editorial score→color for win-rate / rubric bars (shared across scoreboard + qualitative). */
function scoreColor(score) {
  // Low muted orange/red → mid orange → high deep blue (site Compare palette).
  const stops = [
    [0, [143, 61, 12]],    // #8f3d0c
    [0.4, [196, 90, 26]],   // #c45a1a
    [0.55, [217, 111, 49]], // #d96f31
    [0.72, [47, 111, 203]], // #2f6fcb
    [1, [22, 63, 132]],     // #163f84
  ];
  const t = Math.max(0, Math.min(1, Number(score) / 10));
  let i = 0;
  while (i < stops.length - 2 && t > stops[i + 1][0]) i += 1;
  const [t0, c0] = stops[i];
  const [t1, c1] = stops[i + 1];
  const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
  const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
  const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
  const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
  return `rgb(${r},${g},${b})`;
}

function records(mode, judge = "aggregate", runId = state.runId, opts = {}) {
  const bundle = activeData(runId);
  const source = judge === "aggregate" ? bundle?.aggregate : bundle?.by_judge;
  if (!Array.isArray(source)) return [];
  const allow = opts.allModels ? () => true : modelAllowed;
  return source.filter(d =>
    d.mode === mode &&
    allow(d.model_label) &&
    (judge === "aggregate" || d.judge_model === judge) &&
    !isOwnFamily(judge, d.model_label)
  );
}

function rankOfRanks(mode, judge = "aggregate", runId = state.runId, opts = {}) {
  const rows = [];
  for (const task of taskOrder) {
    const sub = records(mode, judge, runId, opts)
      .filter(d => d.task_slug === task)
      .sort((a, b) => num(a.rank_value) - num(b.rank_value) || num(b.score) - num(a.score) || a.model_label.localeCompare(b.model_label));
    sub.forEach((d, i) => rows.push({ ...d, display_rank: i + 1 }));
  }
  return rows;
}

function rankingsJudge() {
  return state.rankings?.judgeFilter || "aggregate";
}

/** Task-Usage Scoreboard always uses the full candidate pool (no model-pool filter). */
function rankingRows(mode = state.mode, judge = rankingsJudge(), runId = state.runId) {
  return rankOfRanks(mode, judge, runId, { allModels: true }).filter(d => d.task_slug === state.task);
}

/** Judges with ranking rows for the current task × mode (leave-family-out already in records). */
function rankingJudgeOptions() {
  const bundle = activeData();
  const seen = new Map();
  (bundle?.by_judge || []).forEach(d => {
    if (d.mode !== state.mode || d.task_slug !== state.task || !d.judge_model) return;
    if (isOwnFamily(d.judge_model, d.model_label)) return;
    if (!seen.has(d.judge_model)) seen.set(d.judge_model, judgeDisplay(d.judge_model));
  });
  return [...seen.entries()]
    .map(([model, label]) => ({ model, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function renderRankJudgeBar() {
  const el = document.getElementById("rankJudgeBar");
  if (!el) return;
  if (!state.rankings) state.rankings = { judgeFilter: "aggregate" };
  const judgeOpts = rankingJudgeOptions();
  const active = rankingsJudge();
  if (active !== "aggregate" && !judgeOpts.some(j => j.model === active)) {
    state.rankings.judgeFilter = "aggregate";
  }
  const judge = rankingsJudge();
  const buttons = [
    `<button type="button" class="compare-judge-chip ${judge === "aggregate" ? "active" : ""}" data-rank-judge="aggregate">Average</button>`,
    ...judgeOpts.map(j =>
      `<button type="button" class="compare-judge-chip ${judge === j.model ? "active" : ""}" data-rank-judge="${esc(j.model)}">${esc(j.label)}</button>`
    ),
  ].join("");
  el.innerHTML = `
    <span class="compare-judge-bar-label">Scores from</span>
    <div class="compare-judge-chips">${buttons}</div>
    <span class="compare-rubric-scope">Average = panel aggregate · per-judge respects leave-family-out</span>`;
  el.querySelectorAll("[data-rank-judge]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.rankings.judgeFilter = btn.dataset.rankJudge;
      state.rubricFocus = null;
      renderRankings();
    });
  });
}

function renderRankings() {
  renderRankJudgeBar();
  renderLeaderboard();
  renderRubric();
}

function averageRanks(judge = "aggregate", runId = state.runId) {
  const out = {};
  for (const mode of ["augmentation", "automation"]) {
    for (const d of rankOfRanks(mode, judge, runId)) {
      out[d.model_label] ||= {};
      out[d.model_label][mode] ||= [];
      out[d.model_label][mode].push(d.display_rank);
    }
  }
  return Object.entries(out).map(([model, v]) => ({
    model,
    augmentation: v.augmentation ? avg(v.augmentation) : null,
    automation: v.automation ? avg(v.automation) : null,
  })).filter(d => d.augmentation !== null && d.automation !== null);
}

/** Paper Fig. 9: mean ranks across all replicate runs (assistant models by default). */
function panelAverageRanks(judge = "aggregate", { assistantsOnly = true } = {}) {
  const buckets = new Map();
  for (const run of runList()) {
    for (const d of averageRanks(judge, run.id)) {
      if (assistantsOnly && isBaselineModel(d.model)) continue;
      const cur = buckets.get(d.model) || { automation: [], augmentation: [] };
      cur.automation.push(d.automation);
      cur.augmentation.push(d.augmentation);
      buckets.set(d.model, cur);
    }
  }
  return [...buckets.entries()].map(([model, v]) => ({
    model,
    automation: avg(v.automation),
    augmentation: avg(v.augmentation),
  }));
}

function rankToScore(rank, maxRank) {
  return maxRank + 1 - Number(rank);
}

function avg(xs) {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function uniqueJudgmentCount(bundle) {
  const seen = new Set();
  Object.entries(bundle.runs || {}).forEach(([taskMode, run]) => {
    (run.judgments || []).forEach(j => {
      const a = Math.min(Number(j.left_idx), Number(j.right_idx));
      const b = Math.max(Number(j.left_idx), Number(j.right_idx));
      seen.add(`${taskMode}|${j.judge_model}|${a}|${b}`);
    });
  });
  return seen.size;
}

function heatColor(rank, maxRank) {
  if (!rank) return "#f2f4f7";
  const t = (rank - 1) / Math.max(1, maxRank - 1);
  const stops = [
    [37, 127, 99],
    [210, 232, 207],
    [244, 221, 124],
    [222, 105, 72],
    [158, 35, 42],
  ];
  const p = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(p));
  const f = p - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function heatModelAbbr(model, mode) {
  if (model === "plain") return "Plain";
  return modelShort[model] || displayModel(model, mode).slice(0, 5);
}

function heatModelHeader(model, mode) {
  const full = displayModel(model, mode);
  const abbr = heatModelAbbr(model, mode);
  return `<th scope="col" class="heat-model-col" tabindex="0" data-tip="${esc(full)}" data-tip-title="Model">${esc(abbr)}</th>`;
}

function heatColorLegendHtml() {
  return `<div class="heat-color-legend"><span>Rank 1 · best</span><div class="heat-color-bar"></div><span>worst</span></div>`;
}

function modelLegendHtml(models, mode) {
  return `<div class="model-legend">${models.map(m => `<button type="button" class="model-legend-chip" data-tip="${esc(displayModel(m, mode))}" data-tip-title="${esc(heatModelAbbr(m, mode))}"><b>${esc(heatModelAbbr(m, mode))}</b><span>${esc(displayModel(m, mode))}</span></button>`).join("")}</div>`;
}

let activeTipAnchor = null;

function hideFloatingTip() {
  document.querySelectorAll(".floating-tip").forEach(n => n.remove());
  activeTipAnchor = null;
}

function showFloatingTip(anchor, text, title = "") {
  if (!text) return;
  hideFloatingTip();
  const tip = document.createElement("div");
  tip.className = "floating-tip";
  tip.innerHTML = title
    ? `<div class="floating-tip-title">${esc(title)}</div><div class="floating-tip-body">${esc(text)}</div>`
    : `<div class="floating-tip-body">${esc(text)}</div>`;
  document.body.appendChild(tip);
  const r = anchor.getBoundingClientRect();
  let left = Math.max(8, Math.min(r.left, window.innerWidth - tip.offsetWidth - 8));
  let top = r.bottom + 8;
  if (top + tip.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - tip.offsetHeight - 8);
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
  activeTipAnchor = anchor;
}

function bindFloatingTips(root = document) {
  root.querySelectorAll("[data-tip]").forEach(el => {
    if (el.dataset.tipBound) return;
    el.dataset.tipBound = "1";
    const text = el.dataset.tip || "";
    const title = el.dataset.tipTitle || "";
    if (el.classList.contains("term-info-btn")) {
      el.addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        if (activeTipAnchor === el) hideFloatingTip();
        else showFloatingTip(el, text, title);
      });
      return;
    }
    el.addEventListener("mouseenter", () => showFloatingTip(el, text, title));
    el.addEventListener("mouseleave", hideFloatingTip);
    el.addEventListener("focus", () => showFloatingTip(el, text, title));
    el.addEventListener("blur", hideFloatingTip);
    el.addEventListener("click", e => {
      e.stopPropagation();
      showFloatingTip(el, text, title);
    });
  });
}

function heatmapsJudge() {
  return state.heatmaps?.judgeFilter || "aggregate";
}

/** Judges available for Single-run Result (full panel; leave-family-out applied per cell). */
function heatmapJudgeOptions() {
  const bundle = activeData();
  const seen = new Map();
  (bundle?.by_judge || []).forEach(d => {
    if (!d.judge_model) return;
    if (!seen.has(d.judge_model)) seen.set(d.judge_model, judgeDisplay(d.judge_model));
  });
  return [...seen.entries()]
    .map(([model, label]) => ({ model, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function renderHeatJudgeBar() {
  const el = document.getElementById("heatJudgeBar");
  if (!el) return;
  if (!state.heatmaps) state.heatmaps = { judgeFilter: "aggregate" };
  const judgeOpts = heatmapJudgeOptions();
  const active = heatmapsJudge();
  if (active !== "aggregate" && !judgeOpts.some(j => j.model === active)) {
    state.heatmaps.judgeFilter = "aggregate";
  }
  const judge = heatmapsJudge();
  const buttons = [
    `<button type="button" class="compare-judge-chip ${judge === "aggregate" ? "active" : ""}" data-heat-judge="aggregate">Average</button>`,
    ...judgeOpts.map(j =>
      `<button type="button" class="compare-judge-chip ${judge === j.model ? "active" : ""}" data-heat-judge="${esc(j.model)}">${esc(j.label)}</button>`
    ),
  ].join("");
  el.innerHTML = `
    <span class="compare-judge-bar-label">Scores from</span>
    <div class="compare-judge-chips">${buttons}</div>
    <span class="compare-rubric-scope">Average = panel aggregate · per-judge respects leave-family-out</span>`;
  el.querySelectorAll("[data-heat-judge]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.heatmaps.judgeFilter = btn.dataset.heatJudge;
      renderHeatmaps();
    });
  });
}

function renderHeatmap(el, mode) {
  if (!el) return;
  const judge = heatmapsJudge();
  /** Single-run Result always uses the full candidate pool (same as Task-Usage Scoreboard). */
  const rows = rankOfRanks(mode, judge, state.runId, { allModels: true });
  const models = [...new Set(rows.map(d => d.model_label))].sort((a, b) => {
    const avs = rows.filter(d => d.model_label === a).map(d => d.display_rank);
    const bvs = rows.filter(d => d.model_label === b).map(d => d.display_rank);
    const av = avs.length ? avg(avs) : 999;
    const bv = bvs.length ? avg(bvs) : 999;
    return av - bv;
  });
  const maxRank = models.length;
  const byKey = new Map(rows.map(d => [`${d.task_slug}|${d.model_label}`, d]));
  let html = `<table class="heat-table compact-heat"><thead><tr><th scope="col">Task</th>${models.map(m => heatModelHeader(m, mode)).join("")}</tr></thead><tbody>`;
  for (const task of taskOrder) {
    html += `<tr><th scope="row">${cleanTaskTitle(task)}</th>`;
    for (const model of models) {
      const d = byKey.get(`${task}|${model}`);
      const r = d?.display_rank;
      const full = displayModel(model, mode);
      if (isOwnFamily(judge, model)) {
        html += `<td class="heat-na" data-tip="${esc(full)} excluded by leave-family-out for ${esc(judgeLabels[judge] || judge)}." data-tip-title="N/A">—</td>`;
      } else {
        const tip = `${full} · ${cleanTaskTitle(task)} · rank ${r || "—"} · win rate ${d ? Number(d.score).toFixed(3) : "NA"}`;
        html += `<td data-tip="${esc(tip)}" data-tip-title="Cell" style="background:${heatColor(r, maxRank)};color:${r > maxRank * .72 ? "white" : "#172033"}">${r || ""}</td>`;
      }
    }
    html += `</tr>`;
  }
  html += `<tr><th scope="row">Average</th>`;
  for (const model of models) {
    if (isOwnFamily(judge, model)) {
      html += `<td class="heat-na">—</td>`;
    } else {
      const vals = rows.filter(d => d.model_label === model).map(d => d.display_rank);
      const av = vals.length ? avg(vals) : null;
      html += av ? `<td style="background:${heatColor(av, maxRank)}">${av.toFixed(1)}</td>` : `<td class="heat-na">—</td>`;
    }
  }
  html += `</tr></tbody></table>`;
  el.innerHTML = heatColorLegendHtml() + html + modelLegendHtml(models, mode);
  bindFloatingTips(el);
}

function renderHeatmaps() {
  renderHeatJudgeBar();
  renderMetrics();
  renderHeatmap(document.getElementById("heatAug"), "augmentation");
  renderHeatmap(document.getElementById("heatAuto"), "automation");
}

function roleLeanMeta(gap) {
  if (gap >= 0.8) return { lean: "aug", label: "Stronger assistant", short: "assistant" };
  if (gap <= -0.8) return { lean: "auto", label: "Stronger automator", short: "automator" };
  return { lean: "bal", label: "Similar in both", short: "similar" };
}

function bindRoleScatterSync(root) {
  const plot = root.querySelector(".role-scatter-svg");
  const list = root.querySelector(".role-model-list");
  if (!plot || !list) return;

  const clear = () => {
    root.querySelectorAll(".role-point.is-active, .role-model-row.is-active").forEach(n => n.classList.remove("is-active"));
    root.classList.remove("role-scatter-has-focus");
  };

  const activate = (model, { scroll = false } = {}) => {
    clear();
    if (!model) return;
    root.classList.add("role-scatter-has-focus");
    const point = [...plot.querySelectorAll(".role-point")].find(n => n.dataset.model === model);
    const row = [...list.querySelectorAll(".role-model-row")].find(n => n.dataset.model === model);
    if (point) point.classList.add("is-active");
    if (row) {
      row.classList.add("is-active");
      if (scroll) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };

  plot.querySelectorAll(".role-point").forEach(point => {
    const model = point.dataset.model;
    point.addEventListener("mouseenter", () => activate(model, { scroll: true }));
    point.addEventListener("mouseleave", clear);
    point.addEventListener("focus", () => activate(model, { scroll: true }));
    point.addEventListener("blur", clear);
  });

  list.querySelectorAll(".role-model-row").forEach(row => {
    const model = row.dataset.model;
    row.addEventListener("mouseenter", () => activate(model));
    row.addEventListener("mouseleave", clear);
    row.addEventListener("focus", () => activate(model));
    row.addEventListener("blur", clear);
  });
}

function renderRoleScatter() {
  const el = document.getElementById("roleScatter");
  if (!el) return;
  const data = panelAverageRanks("aggregate", { assistantsOnly: true });
  if (!data.length) {
    el.innerHTML = `<p class="chart-note">No panel ranks available yet.</p>`;
    return;
  }
  const maxRank = Math.max(
    ...data.flatMap(d => [d.augmentation, d.automation]),
    data.length,
    9
  );
  const scored = data.map(d => {
    const autoScore = rankToScore(d.automation, maxRank);
    const augScore = rankToScore(d.augmentation, maxRank);
    const gap = augScore - autoScore;
    return {
      model: d.model,
      autoScore,
      augScore,
      autoRank: d.automation,
      augRank: d.augmentation,
      gap,
      ...roleLeanMeta(gap),
    };
  });
  const size = 520;
  const pad = 58;
  const lo = 1;
  const hi = maxRank;
  const x = v => pad + (v - lo) / (hi - lo) * (size - pad * 2);
  const y = v => size - pad - (v - lo) / (hi - lo) * (size - pad * 2);
  const mid = (lo + hi) / 2;
  const midX = x(mid);
  const midY = y(mid);
  const plotW = size - pad * 2;
  const plotH = size - pad * 2;
  const ticks = Array.from({ length: Math.round(hi) }, (_, i) => i + 1)
    .filter(t => t === 1 || t === Math.round(hi) || t % 2 === 0);

  const fillByLean = {
    aug: "#2f6fcb",
    auto: "#d96f31",
    bal: "#5a6b82",
  };

  const points = scored.map(d => {
    const cx = x(d.autoScore);
    const cy = y(d.augScore);
    const short = modelShort[d.model] || d.model.slice(0, 6);
    const right = cx < size * 0.72;
    const lx = right ? cx + 12 : cx - 12;
    const anchor = right ? "start" : "end";
    const fill = fillByLean[d.lean] || fillByLean.bal;
    const tip = [
      `Automation reverse rank ${d.autoScore.toFixed(1)} (mean rank ${d.autoRank.toFixed(1)})`,
      `Augmentation reverse rank ${d.augScore.toFixed(1)} (mean rank ${d.augRank.toFixed(1)})`,
      d.label,
    ].join(" · ");
    return `<g class="role-point lean-${d.lean}" tabindex="0" data-model="${esc(d.model)}" data-tip="${esc(tip)}" data-tip-title="${esc(displayModel(d.model))}">
      <circle class="role-hit" cx="${cx}" cy="${cy}" r="14" fill="transparent"/>
      <circle class="role-halo" cx="${cx}" cy="${cy}" r="9" fill="${fill}" opacity="0.18" pointer-events="none"/>
      <circle class="role-dot" cx="${cx}" cy="${cy}" r="5.5" fill="${fill}" stroke="#fff" stroke-width="1.8" filter="url(#roleDotShadow)" pointer-events="none"/>
      <text class="role-label" x="${lx}" y="${cy + 3.5}" font-size="11" font-weight="700" text-anchor="${anchor}" fill="#172033" stroke="white" stroke-width="3.5" paint-order="stroke" style="stroke-linejoin:round" pointer-events="none">${short}</text>
    </g>`;
  }).join("");

  const qLabel = (tx, ty, text, anchor = "middle", cls = "") =>
    `<text class="role-q-label ${cls}" x="${tx}" y="${ty}" text-anchor="${anchor}" font-size="10.5" font-weight="700">${text}</text>`;

  const svg = `<div class="svg-wrap landing-scatter-wrap"><svg class="role-scatter-svg" viewBox="0 0 ${size} ${size}" role="img" aria-label="Models plotted by automation reverse rank versus augmentation reverse rank. Higher is better on both axes.">
    <defs>
      <filter id="roleDotShadow" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-color="#1f2433" flood-opacity="0.18"/>
      </filter>
    </defs>
    <rect x="0" y="0" width="${size}" height="${size}" fill="#f7f9fc"/>
    <g class="role-quadrants" aria-hidden="true">
      <rect class="q-aug" x="${pad}" y="${pad}" width="${midX - pad}" height="${midY - pad}" />
      <rect class="q-both" x="${midX}" y="${pad}" width="${pad + plotW - midX}" height="${midY - pad}" />
      <rect class="q-weak" x="${pad}" y="${midY}" width="${midX - pad}" height="${pad + plotH - midY}" />
      <rect class="q-auto" x="${midX}" y="${midY}" width="${pad + plotW - midX}" height="${pad + plotH - midY}" />
    </g>
    <rect x="${pad}" y="${pad}" width="${plotW}" height="${plotH}" fill="none" stroke="#d9dee7"/>
    ${ticks.map(t => {
      const s = rankToScore(t, maxRank);
      return `<line x1="${x(s)}" y1="${pad}" x2="${x(s)}" y2="${size - pad}" stroke="#e8edf4"/><line x1="${pad}" y1="${y(s)}" x2="${size - pad}" y2="${y(s)}" stroke="#e8edf4"/><text x="${x(s)}" y="${size - pad + 18}" text-anchor="middle" font-size="10" fill="#657083">${s}</text><text x="${pad - 10}" y="${y(s) + 3}" text-anchor="end" font-size="10" fill="#657083">${s}</text>`;
    }).join("")}
    <line x1="${x(lo)}" y1="${y(lo)}" x2="${x(hi)}" y2="${y(hi)}" stroke="#8a93a3" stroke-dasharray="5 5" stroke-width="1.4"/>
    <text x="${(x(lo) + x(hi)) / 2 + 18}" y="${(y(lo) + y(hi)) / 2 - 10}" text-anchor="middle" font-size="10" fill="#7a8496" font-style="italic">Same in both roles</text>
    ${qLabel(pad + 10, pad + 16, "Stronger assistant", "start", "q-aug-label")}
    ${qLabel(size - pad - 10, pad + 16, "Strong in both", "end", "q-both-label")}
    ${qLabel(pad + 10, size - pad - 10, "Weaker in both", "start", "q-weak-label")}
    ${qLabel(size - pad - 10, size - pad - 10, "Stronger automator", "end", "q-auto-label")}
    <g class="role-points">${points}</g>
    <text x="${size / 2}" y="${size - 8}" text-anchor="middle" font-size="12" font-weight="700" fill="#1f2433">Automation reverse rank →</text>
    <text x="14" y="${size / 2}" text-anchor="middle" font-size="12" font-weight="700" fill="#1f2433" transform="rotate(-90 14 ${size / 2})">← Augmentation reverse rank</text>
  </svg></div>`;

  const rows = [...scored]
    .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap) || b.autoScore + b.augScore - (a.autoScore + a.augScore));

  const listRows = rows.map(d => {
    const delta = Math.abs(d.gap);
    const leanNote = d.lean === "bal"
      ? "similar both ways"
      : d.lean === "aug"
        ? `+${delta.toFixed(1)} as assistant`
        : `+${delta.toFixed(1)} as automator`;
    return `<button type="button" class="role-model-row lean-${d.lean}" data-model="${esc(d.model)}">
      <span class="role-model-main">
        <span class="role-model-name">${esc(displayModel(d.model))}</span>
        <span class="role-model-lean">${esc(leanNote)}</span>
      </span>
      <span class="role-model-scores" aria-label="Reverse rank scores">
        <span class="role-score role-score-auto"><em>Auto</em><b>${d.autoScore.toFixed(1)}</b></span>
        <span class="role-score role-score-aug"><em>Aug</em><b>${d.augScore.toFixed(1)}</b></span>
      </span>
    </button>`;
  }).join("");

  el.innerHTML = `
    <p class="chart-note">10-run panel average · reverse rank (higher = better) · assistant models only</p>
    <div class="role-swap-layout">
      <div class="role-swap-left">${svg}</div>
      <div class="role-swap-right">
        <div class="role-info role-model-panel">
          <div class="role-info-head">All models</div>
          <p class="role-info-sub">Reverse rank scores. Hover a point or row to sync. Sorted by role gap.</p>
          <div class="role-model-list" role="list">${listRows}</div>
        </div>
      </div>
    </div>`;
  bindFloatingTips(el);
  bindRoleScatterSync(el);
}

function renderMetrics() {
  const el = document.getElementById("metricRow");
  if (!el) return;
  const tasks = state.data.tasks.length;
  const stats = runStats();
  const bundle = activeData();
  const outputs = stats?.outputs ?? Object.values(bundle.runs || {}).reduce((s, r) => s + (r.outputs?.length || 0), 0);
  const judgments = stats?.unique_judgments ?? uniqueJudgmentCount(bundle);
  const models = new Set((bundle.aggregate || []).map(d => d.model_label)).size;
  el.innerHTML = [
    [`${activeRunMeta().label}`, "selected run"],
    [`${tasks}`, "tasks"],
    [`${models}`, "models tested"],
    [`${outputs}`, "saved outputs"],
    [`${judgments.toLocaleString()}`, "unique pairwise judgments"],
  ].map(([v, l]) => `<div class="metric"><b>${v}</b><span>${l}</span></div>`).join("");
}

function renderLeaderboard() {
  const titleEl = document.getElementById("rankTitle");
  const subEl = document.getElementById("rankSubtitle");
  const board = document.getElementById("leaderboard");
  if (!titleEl || !board) return;
  const judge = rankingsJudge();
  const judgeLabel = judge === "aggregate" ? "Average" : (judgeLabels[judge] || judgeDisplay(judge));
  const rows = rankingRows().sort((a, b) => a.display_rank - b.display_rank);
  titleEl.textContent = `${cleanTaskTitle(state.task)} · ${modeLabels[state.mode]}`;
  if (subEl) {
    subEl.textContent = `${judgeLabel} · click a model to load its rubric dimension scores`;
  }
  if (!rows.length) {
    board.innerHTML = `<div class="rank-empty-state"><p>No ranked models for this task under the current judge filter.</p><p class="rank-empty-hint">Try <b>Average</b>, another task, or switch usage regime.</p></div>`;
    return;
  }
  const models = rows.map(d => d.model_label);
  if (!state.selectedModel || !models.includes(state.selectedModel)) {
    state.selectedModel = models[0];
  }
  const maxScore = Math.max(...rows.map(d => Number(d.score)), 1);
  board.innerHTML = `<p class="leaderboard-hint">All candidates · pairwise win rate. Selecting a model updates rubric scores on the right.</p>` + rows
    .map(d => {
      const rank = Number(d.display_rank);
      const win = Number(d.score);
      const rawRank = num(d.rank_value);
      const active = state.selectedModel === d.model_label;
      return `<div class="rank-row ${active ? "is-selected" : ""}">
        <button type="button" class="rank-model-btn ${active ? "active" : ""}" data-rankmodel="${esc(d.model_label)}" aria-pressed="${active ? "true" : "false"}">
          <span class="rank-badge ${rank <= 3 ? "top" : ""}">${rank}</span>
          <span class="rank-model-copy">
            <span class="rank-model-name">${esc(displayModel(d.model_label, state.mode))}</span>
            <span class="leader-meta">${esc(judgeLabel)}${Number.isFinite(rawRank) ? ` · avg output rank ${rawRank.toFixed(2)}` : ""}</span>
          </span>
        </button>
        <div class="bar-track" title="Pairwise win rate"><div class="bar-fill" style="width:${win / maxScore * 100}%;background:${scoreColor(win * 10)}"></div></div>
        <span class="rank-win" title="Pairwise win rate">${win.toFixed(2)}</span>
      </div>`;
    })
    .join("");
  board.querySelectorAll("[data-rankmodel]").forEach(b => b.addEventListener("click", () => {
    state.selectedModel = b.dataset.rankmodel;
    state.rubricFocus = null;
    renderLeaderboard();
    renderRubric();
  }));
}

function renderRubric() {
  const chart = document.getElementById("rubricChart");
  const titleEl = document.getElementById("rubricPanelTitle");
  if (!chart) return;
  if (!qualDataReady()) {
    chart.innerHTML = `<p class="qual-loading-inline">Rubric scores load with the qualitative bundle when you open Task-Usage Scoreboard or Qualitative.</p>`;
    return;
  }
  const judge = rankingsJudge();
  const run = currentRun();
  const ranked = rankingRows();
  const allowed = new Set(ranked.map(d => d.model_label));
  const outputs = (run?.outputs || []).filter(o => allowed.has(o.model_label));
  const models = [...new Set(outputs.map(d => d.model_label))];
  if (!models.length && ranked.length) {
    // Rankings exist but qualitative outputs not yet keyed — still pick a model label.
    ranked.forEach(d => models.push(d.model_label));
  }
  const uniqueModels = [...new Set(models)];
  const model = state.selectedModel && uniqueModels.includes(state.selectedModel)
    ? state.selectedModel
    : uniqueModels[0];
  if (model) state.selectedModel = model;
  if (titleEl) {
    titleEl.textContent = model
      ? `${displayModel(model, state.mode)} · dimension scores`
      : "Dimension scores & meanings";
  }
  const output = outputs.find(o => o.model_label === model);
  const judgments = run?.judgments || [];
  const activeJudge = judge === "aggregate" ? null : judge;
  if (activeJudge && output && isOwnFamily(activeJudge, output.model_label)) {
    chart.innerHTML = `<div class="rank-empty-state"><p><b>${esc(displayModel(model, state.mode))}</b> is leave-family-out for <b>${esc(judgeDisplay(activeJudge))}</b>.</p><p class="rank-empty-hint">Switch to Average or another judge that scored this model.</p></div>`;
    return;
  }
  const rubricOpts = activeJudge ? { judgeModel: activeJudge } : {};
  const sub = output
    ? rubricMeansForOutput(output, judgments, state.task, rubricOpts).map(r => ({
      dimension: r.dimension,
      mean_score: r.mean,
      n: r.n,
    }))
    : [];
  const max = 10;
  const nScores = sub[0]?.n || 0;
  const judgeLabel = activeJudge
    ? (judgeLabels[activeJudge] || judgeDisplay(activeJudge))
    : "Average (leave-family-out eligible judges)";
  const intro = `<p class="rank-rubric-intro">Select a model on the left. Hover or click a dimension for what it means on <b>${esc(cleanTaskTitle(state.task))}</b>. Scores average pairwise appearances under <b>${esc(judgeLabel)}</b>${nScores ? ` (n=${nScores})` : ""}.</p>`;
  const body = sub.length
    ? sub.map(d => {
      const focused = state.rubricFocus === d.dimension;
      return `<div class="rank-rubric-row bar-row ${focused ? "is-focus" : ""}" data-rubricdim="${esc(d.dimension)}">
        <div><span class="rubric-label">${esc(rubricName(d.dimension))}</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${Number(d.mean_score) / max * 100}%;background:${scoreColor(d.mean_score)}"></div></div>
        <div class="rank-rubric-val">${Number(d.mean_score).toFixed(1)}</div>
      </div>`;
    }).join("")
    : `<p class="chart-note">No rubric-score rows found for this response under the current judge filter. Try Average or another judge.</p>`;
  const focus = state.rubricFocus && sub.some(d => d.dimension === state.rubricFocus)
    ? state.rubricFocus
    : sub[0]?.dimension;
  if (focus) state.rubricFocus = focus;
  const detail = focus
    ? `<div class="rubric-detail rank-rubric-detail"><span class="rank-rubric-detail-kicker">What this dimension means</span><b>${esc(rubricName(focus))}</b><p>${esc(rubricTip(focus))}</p></div>`
    : "";
  chart.innerHTML = intro + body + detail;
  chart.querySelectorAll("[data-rubricdim]").forEach(el => {
    const setFocus = () => {
      state.rubricFocus = el.dataset.rubricdim;
      chart.querySelectorAll("[data-rubricdim]").forEach(row => {
        row.classList.toggle("is-focus", row.dataset.rubricdim === state.rubricFocus);
      });
      const detailEl = chart.querySelector(".rubric-detail");
      if (detailEl) {
        detailEl.innerHTML = `<span class="rank-rubric-detail-kicker">What this dimension means</span><b>${esc(rubricName(state.rubricFocus))}</b><p>${esc(rubricTip(state.rubricFocus))}</p>`;
      }
    };
    el.addEventListener("mouseenter", setFocus);
    el.addEventListener("click", setFocus);
  });
}

function renderJudgeScatter() {
  const bundle = activeData();
  const scatter = bundle.scatter_points || [];
  const correlations = bundle.correlations || [];
  const byJudge = bundle.by_judge || [];
  const judges = [...new Set(byJudge.map(d => d.judge_model))].filter(Boolean);
  const pairs = [];
  for (let i = 0; i < judges.length; i++) {
    for (let j = i + 1; j < judges.length; j++) pairs.push([judges[i], judges[j]]);
  }
  const size = 420, pad = 50, maxRank = 10;
  const x = v => pad + (v - 1) / (maxRank - 1) * (size - pad * 2);
  const y = v => size - pad - (v - 1) / (maxRank - 1) * (size - pad * 2);
  const stat = (pts, a, b) => {
    const diffs = pts.map(d => Math.abs(Number(d[a]) - Number(d[b])));
    const within1 = diffs.filter(d => d <= 1).length / Math.max(1, diffs.length);
    const meanDiff = diffs.reduce((s, d) => s + d, 0) / Math.max(1, diffs.length);
    const ca = canonicalJudge(a);
    const cb = canonicalJudge(b);
    const corr = correlations.find(d => d.scope === "all" && d.method === "spearman" && (
      (canonicalJudge(d.judge_a) === ca && canonicalJudge(d.judge_b) === cb) ||
      (canonicalJudge(d.judge_a) === cb && canonicalJudge(d.judge_b) === ca)
    ));
    return { within1, meanDiff, rho: corr ? Number(corr.correlation) : null };
  };
  const cardHtml = pairs.map(([a, b]) => {
    const pts = scatter.filter(d => d[a] !== null && d[b] !== null && modelAllowed(d.model_label));
    const s = stat(pts, a, b);
    return `<div class="metric"><b>${s.rho === null ? "NA" : s.rho.toFixed(2)}</b><span>${judgeLabels[a]} × ${judgeLabels[b]} rank correlation<br>${Math.round(s.within1 * 100)}% close calls within 1 rank<br>average rank gap ${s.meanDiff.toFixed(1)}</span></div>`;
  }).join("");
  document.getElementById("judgeAgreementCards").innerHTML = cardHtml;
  const panels = pairs.map(([a, b]) => {
    const pts = scatter.filter(d => d[a] !== null && d[b] !== null && modelAllowed(d.model_label));
    return `<svg viewBox="0 0 ${size} ${size}">
      <rect width="${size}" height="${size}" fill="white"/>
      <text x="${size/2}" y="24" text-anchor="middle" font-weight="700">${judgeLabels[a]} vs ${judgeLabels[b]}</text>
      <text x="${size/2}" y="42" text-anchor="middle" font-size="11" fill="#657083">One point = one model in one task/mode</text>
      ${[1,5,10].map(t => `<text x="${x(t)}" y="${size-pad+22}" text-anchor="middle" font-size="11">${t}</text><text x="${pad-12}" y="${y(t)+4}" text-anchor="end" font-size="11">${t}</text>`).join("")}
      ${Array.from({ length: 10 }, (_, i) => i + 1).map(t => `<line x1="${x(t)}" y1="${pad}" x2="${x(t)}" y2="${size-pad}" stroke="#e6e9ee"/><line x1="${pad}" y1="${y(t)}" x2="${size-pad}" y2="${y(t)}" stroke="#e6e9ee"/>`).join("")}
      <polygon points="${x(1)},${y(2)} ${x(9)},${y(10)} ${x(10)},${y(9)} ${x(2)},${y(1)}" fill="#2f6fcb" opacity=".08"/>
      <line x1="${x(1)}" y1="${y(1)}" x2="${x(10)}" y2="${y(10)}" stroke="#111" stroke-dasharray="7 6"/>
      ${pts.map((d, i) => `<circle cx="${x(d[a]) + ((i % 7) - 3) * 1.8}" cy="${y(d[b]) + (((i / 7) | 0) % 7 - 3) * 1.8}" r="3.8" fill="${d.mode === "augmentation" ? "#2f6fcb" : "#d96f31"}" opacity=".52"><title>${cleanTaskTitle(d.task)} ${d.mode}: ${displayModel(d.model_label, d.mode)}</title></circle>`).join("")}
      <text x="${size/2}" y="${size-10}" text-anchor="middle" font-size="12">${judgeLabels[a]} rank</text>
      <text x="14" y="${size/2}" text-anchor="middle" font-size="12" transform="rotate(-90 14 ${size/2})">${judgeLabels[b]} rank</text>
    </svg>`;
  }).join("");
  document.getElementById("judgeScatter").innerHTML = `<p style="color:var(--muted);font-size:13px;margin:0 0 12px">Dots near the dashed diagonal mean the two judges assigned similar ranks. The pale blue band marks rankings within one rank of each other. Blue dots are augmentation entries; orange dots are automation entries.</p><div class="two-col judge-grid">${panels}</div><h3 style="margin-top:18px">Task-Level Agreement Summary</h3><div id="judgeAgreementTable"></div><h3 style="margin-top:18px">Largest Individual Rank Disagreements</h3><div id="judgeDisagreementTable"></div>`;
  renderJudgeAgreementTable(pairs);
  renderJudgeDisagreementTable(pairs);
  renderCorrTable();
}

function renderJudgeAgreementTable(pairs) {
  const scatter = activeData().scatter_points || [];
  const rows = [];
  for (const task of taskOrder) {
    for (const mode of ["augmentation", "automation"]) {
      const cells = pairs.map(([a, b]) => {
        const pts = scatter.filter(d => d.task === task && d.mode === mode && d[a] !== null && d[b] !== null && modelAllowed(d.model_label));
        if (!pts.length) return "N/A";
        const diffs = pts.map(d => Math.abs(Number(d[a]) - Number(d[b])));
        const meanGap = diffs.reduce((s, d) => s + d, 0) / diffs.length;
        const within1 = diffs.filter(d => d <= 1).length / diffs.length;
        return `${meanGap.toFixed(1)} gap / ${Math.round(within1 * 100)}% close`;
      });
      rows.push({ task, mode, cells });
    }
  }
  const headers = pairs.map(([a, b]) => `${judgeLabels[a]} × ${judgeLabels[b]}`);
  document.getElementById("judgeAgreementTable").innerHTML = `<p style="color:var(--muted);font-size:12px;margin:6px 0 10px">Each cell reports average absolute rank difference, then the share of model ranks within one position of each other. Lower gap and higher close-share indicate better agreement.</p><table class="heat-table"><thead><tr><th>Task / Mode</th>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr><td>${cleanTaskTitle(r.task)} / ${modeLabels[r.mode]}</td>${r.cells.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function renderJudgeDisagreementTable(pairs) {
  const scatter = activeData().scatter_points || [];
  const rows = [];
  for (const [a, b] of pairs) {
    scatter
      .filter(d => d[a] !== null && d[b] !== null && modelAllowed(d.model_label))
      .forEach(d => {
        rows.push({
          pair: `${judgeLabels[a]} × ${judgeLabels[b]}`,
          task: d.task,
          mode: d.mode,
          model: d.model_label,
          aRank: Number(d[a]),
          bRank: Number(d[b]),
          gap: Math.abs(Number(d[a]) - Number(d[b])),
        });
      });
  }
  rows.sort((a, b) => b.gap - a.gap || a.task.localeCompare(b.task));
  const top = rows.slice(0, 12);
  document.getElementById("judgeDisagreementTable").innerHTML = `<p style="color:var(--muted);font-size:12px;margin:6px 0 10px">These are the individual model-task-mode entries where two judges disagreed most about rank. Useful for targeted qualitative audit.</p><table class="heat-table"><thead><tr><th>Pair</th><th>Task / Mode</th><th>Model</th><th>Ranks</th><th>Gap</th></tr></thead><tbody>${top.map(r => `<tr><td>${r.pair}</td><td>${cleanTaskTitle(r.task)} / ${modeLabels[r.mode]}</td><td>${displayModel(r.model, r.mode)}</td><td>${r.aRank} vs ${r.bRank}</td><td>${r.gap}</td></tr>`).join("")}</tbody></table>`;
}

function renderCorrTable() {
  const rows = (activeData().correlations || []).filter(d => d.method === "spearman");
  document.getElementById("corrTable").innerHTML = `<p style="color:var(--muted);font-size:12px;margin:0 0 10px">Spearman is a rank-order correlation. It is computed only on entries both judges were eligible to score after leave-family-out exclusions.</p><table class="heat-table"><thead><tr><th>Scope</th><th>Pair</th><th>Spearman</th><th>Shared ranks</th></tr></thead><tbody>${rows.map(d => `<tr><td>${d.scope}</td><td>${judgeDisplay(d.judge_a)} × ${judgeDisplay(d.judge_b)}</td><td>${Number(d.correlation).toFixed(3)}</td><td>${d.n_pairs}</td></tr>`).join("")}</tbody></table>`;
}

function std(xs) {
  if (!xs.length) return 0;
  const m = avg(xs);
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length);
}

function sem(xs) {
  if (!xs.length) return 0;
  return std(xs) / Math.sqrt(xs.length);
}

/** 10-Run Result always uses the full candidate pool (same as Single-run / Scoreboard). */
function replicateRankRows(mode, judge = "aggregate") {
  return runList().flatMap(run => rankOfRanks(mode, judge, run.id, { allModels: true }).map(d => ({
    ...d,
    run_id: run.id,
    run_label: run.label,
  })));
}

function replicateCellStats(mode, judge = "aggregate") {
  const rows = replicateRankRows(mode, judge);
  const byCell = new Map();
  rows.forEach(d => {
    const key = `${d.task_slug}|${d.model_label}`;
    const arr = byCell.get(key) || [];
    arr.push(Number(d.display_rank));
    byCell.set(key, arr);
  });
  return { rows, byCell };
}

function wrapTableScroll(html, note = "") {
  return `<div class="table-scroll-wrap">${note ? `<p class="table-scroll-note">${note}</p>` : ""}<div class="table-scroll">${html}</div></div>`;
}

function renderReplicateHeatmap(el, mode) {
  const { rows, byCell } = replicateCellStats(mode);
  const models = [...new Set(rows.map(d => d.model_label))].sort((a, b) => {
    const av = avg(rows.filter(d => d.model_label === a).map(d => Number(d.display_rank)));
    const bv = avg(rows.filter(d => d.model_label === b).map(d => Number(d.display_rank)));
    return av - bv;
  });
  const maxRank = Math.max(models.length, 1);
  let html = `<table class="heat-table replicate-heat compact-heat"><thead><tr><th scope="col">Task</th>${models.map(m => heatModelHeader(m, mode)).join("")}</tr></thead><tbody>`;
  for (const task of taskOrder) {
    html += `<tr><th scope="row">${cleanTaskTitle(task)}</th>`;
    for (const model of models) {
      const vals = byCell.get(`${task}|${model}`) || [];
      if (!vals.length) {
        html += `<td class="heat-na">—</td>`;
      } else {
        const m = avg(vals);
        const se = sem(vals);
        const tip = `${displayModel(model, mode)} · ${cleanTaskTitle(task)} · mean ${m.toFixed(2)} ± ${se.toFixed(2)} (${vals.length} runs)`;
        html += `<td data-tip="${esc(tip)}" data-tip-title="10-run cell" style="background:${heatColor(m, maxRank)};color:${m > maxRank * .72 ? "white" : "#172033"}"><b>${m.toFixed(1)}</b><small>±${se.toFixed(1)}</small></td>`;
      }
    }
    html += `</tr>`;
  }
  html += `<tr><th scope="row">Average</th>`;
  for (const model of models) {
    const vals = rows.filter(d => d.model_label === model).map(d => Number(d.display_rank));
    const m = vals.length ? avg(vals) : null;
    const se = vals.length ? sem(vals) : null;
    html += m === null ? `<td class="heat-na">—</td>` : `<td data-tip="Mean ± SE across ${vals.length} run-task cells" data-tip-title="Average" style="background:${heatColor(m, maxRank)}"><b>${m.toFixed(1)}</b><small>±${se.toFixed(1)}</small></td>`;
  }
  html += `</tr></tbody></table>`;
  el.innerHTML = heatColorLegendHtml() + html + modelLegendHtml(models, mode);
  bindFloatingTips(el);
}

function renderReplicateStability(el, mode) {
  const stats = replicateModelStats(mode);
  const tableId = `stability-${mode}-${el.id}`;
  const summary = `<table class="heat-table stability-table compact-stability"><thead><tr><th>Model</th><th>Mean rank</th><th>SD</th><th>Best</th><th>Worst</th><th>Top-3%</th><th aria-hidden="true"></th></tr></thead><tbody>${stats.map((d, i) => `<tr class="stability-row" data-stability-row="${tableId}-${i}"><td>${displayModel(d.model, mode)}</td><td>${d.mean.toFixed(2)}</td><td>${d.sd.toFixed(2)}</td><td>${d.best.toFixed(2)}</td><td>${d.worst.toFixed(2)}</td><td>${Math.round(d.top3 * 100)}%</td><td class="row-chevron-cell" aria-hidden="true">›</td></tr>`).join("")}</tbody></table>`;
  const details = stats.map((d, i) => `<div class="stability-detail hidden" id="${tableId}-${i}"><div class="stability-detail-head">${displayModel(d.model, mode)} · per-run average ranks</div><div class="stability-run-grid">${d.perRun.map(r => `<span class="stability-run-chip"><b>${esc(r.run)}</b> ${r.value.toFixed(2)}</span>`).join("")}</div></div>`).join("");
  el.innerHTML = wrapTableScroll(summary, "Click any model row to expand per-run averages.") + `<div class="stability-details">${details}</div>`;
  el.querySelectorAll(".stability-row").forEach(row => {
    row.style.cursor = "pointer";
    row.addEventListener("click", () => {
      const id = row.dataset.stabilityRow;
      const panel = document.getElementById(id);
      if (!panel) return;
      const open = !panel.classList.contains("hidden");
      el.querySelectorAll(".stability-detail").forEach(p => p.classList.add("hidden"));
      el.querySelectorAll(".stability-row").forEach(r => r.classList.remove("active"));
      if (!open) {
        panel.classList.remove("hidden");
        row.classList.add("active");
      }
    });
  });
}

function replicateModelStats(mode) {
  const rows = replicateRankRows(mode);
  const models = [...new Set(rows.map(d => d.model_label))];
  return models.map(model => {
    const perRun = runList().map(run => {
      const vals = rows.filter(d => d.model_label === model && d.run_id === run.id).map(d => Number(d.display_rank));
      return { run: run.label, value: vals.length ? avg(vals) : null };
    }).filter(d => d.value !== null);
    const allTaskRanks = rows.filter(d => d.model_label === model).map(d => Number(d.display_rank));
    const values = perRun.map(d => d.value);
    return {
      model,
      mean: values.length ? avg(values) : null,
      sd: values.length ? std(values) : null,
      best: values.length ? Math.min(...values) : null,
      worst: values.length ? Math.max(...values) : null,
      top3: allTaskRanks.length ? allTaskRanks.filter(x => x <= 3).length / allTaskRanks.length : null,
      perRun,
    };
  }).filter(d => d.mean !== null).sort((a, b) => a.mean - b.mean);
}

function renderReplicateSummary() {
  renderReplicateHeatmap(document.getElementById("repHeatAug"), "augmentation");
  renderReplicateHeatmap(document.getElementById("repHeatAuto"), "automation");
  renderReplicateStability(document.getElementById("repStabilityAug"), "augmentation");
  renderReplicateStability(document.getElementById("repStabilityAuto"), "automation");
  const aug = replicateModelStats("augmentation");
  const auto = replicateModelStats("automation");
  const stable = xs => xs.length ? avg(xs.map(d => d.sd)).toFixed(2) : "NA";
  document.getElementById("replicateMetrics").innerHTML = [
    [`${runList().length}`, "replicate runs"],
    [displayModel(aug[0]?.model || "", "augmentation"), "best mean augmentation rank"],
    [displayModel(auto[0]?.model || "", "automation"), "best mean automation rank"],
    [`${stable(aug)} / ${stable(auto)}`, "mean rank SD: aug / auto"],
  ].map(([v, l]) => `<div class="metric"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join("");
}

function isBaselineModel(model) {
  return model === "plain" || model === "GPT-3.5-Turbo" || model === "gpt-3.5-turbo";
}

function taskPodiumStats(mode) {
  const rows = replicateRankRows(mode, "aggregate");
  return taskOrder.map(task => {
    const byModel = new Map();
    rows.filter(d => d.task_slug === task).forEach(d => {
      const arr = byModel.get(d.model_label) || [];
      arr.push(Number(d.display_rank));
      byModel.set(d.model_label, arr);
    });
    const candidates = [...byModel.entries()].map(([model, vals]) => ({
      task,
      model,
      mean: avg(vals),
      se: sem(vals),
      n: vals.length,
    })).sort((a, b) => a.mean - b.mean || a.model.localeCompare(b.model));
    return {
      task,
      first: candidates[0] || null,
      second: candidates[1] || null,
    };
  });
}

function taskWinnerStats(mode) {
  return taskPodiumStats(mode).map(d => d.first).filter(Boolean);
}

function taskMetaBySlug(slug) {
  return (state.data?.tasks || []).find(t => t.slug === slug) || null;
}

function taskSourceLabel(slug) {
  return taskSourceHints[slug] || "Designed task";
}

function judgeCoverageStats() {
  let cells = 0;
  let allFour = 0;
  const counts = new Map();
  runList().forEach(run => {
    activeData(run.id).validations.forEach(v => {
      const judges = v.validation?.aggregate_judges || [];
      cells += 1;
      if (judges.length >= 4) allFour += 1;
      judges.forEach(j => counts.set(j, (counts.get(j) || 0) + 1));
    });
  });
  return { cells, allFour, counts };
}

function winnerListHtml(winners, mode) {
  return `<div class="winner-pills">${winners.map(w => `<span class="winner-pill"><b>${esc(cleanTaskTitle(w.task))}</b>${esc(displayModel(w.model, mode))} <em>${w.mean.toFixed(1)}</em></span>`).join("")}</div>`;
}

function countRegimeDivergence() {
  const augWinners = taskWinnerStats("augmentation");
  const autoWinners = taskWinnerStats("automation");
  const augByTask = new Map(augWinners.map(w => [w.task, w.model]));
  const autoByTask = new Map(autoWinners.map(w => [w.task, w.model]));
  let differ = 0;
  let plainWins = 0;
  for (const task of taskOrder) {
    if (augByTask.get(task) === "plain") plainWins += 1;
    if (augByTask.get(task) !== autoByTask.get(task)) differ += 1;
  }
  return { differ, plainWins, total: taskOrder.length };
}

function renderHeroStatBand() {
  const el = document.getElementById("heroStatBand");
  if (!el || !state.data) return;
  const { differ, plainWins, total } = countRegimeDivergence();
  el.innerHTML = [
    { value: `${differ}/${total}`, label: "tasks where automation and augmentation winners differ" },
    { value: `${plainWins}/${total}`, label: "tasks where the unaided worker beats every assisted condition" },
    { value: "10", label: "independent replications in paper figures (±SE = SD/√10)" },
  ].map(s => `<div class="hero-stat"><b>${esc(s.value)}</b><span>${esc(s.label)}</span></div>`).join("");
}

function renderOverviewTakeaways() {
  const el = document.getElementById("overviewTakeaways");
  if (!el || !state.data) return;
  const { differ, plainWins, total } = countRegimeDivergence();
  const augByTask = new Map(taskWinnerStats("augmentation").map(w => [w.task, w.model]));
  const autoByTask = new Map(taskWinnerStats("automation").map(w => [w.task, w.model]));
  const shared = taskOrder.filter(task => augByTask.get(task) && augByTask.get(task) === autoByTask.get(task)).map(cleanTaskTitle);
  el.innerHTML = [
    {
      value: `${differ} of ${total} tasks`,
      text: "The best model in automation is not the best model in augmentation.",
    },
    {
      value: `${plainWins} of ${total} tasks`,
      text: "The unaided worker beats every assisted condition — poor assistance can hurt.",
    },
    {
      value: shared.length ? shared.join(" & ") : "Task-specific",
      text: shared.length
        ? `GPT-5-Mini wins both regimes on ${shared.join(" and ")}; other tasks diverge by role.`
        : "Augmentation rankings are task-specific; no single assistant dominates.",
    },
  ].map(card => `<div class="takeaway-card"><b>${esc(card.value)}</b><p>${esc(card.text)}</p></div>`).join("");
}

function renderOverviewTasks() {
  const list = document.getElementById("overviewTaskList");
  const detail = document.getElementById("overviewTaskDetail");
  if (!list || !detail || !state.data?.tasks?.length) return;
  if (!taskOrder.includes(state.overviewTask)) state.overviewTask = taskOrder[0];
  const tasks = taskOrder.map(slug => taskMetaBySlug(slug)).filter(Boolean);
  list.innerHTML = tasks.map((t, i) => {
    const active = t.slug === state.overviewTask;
    const tone = taskTypeClass(t.type);
    const blurb = taskTagline(t.slug) || t.type || "Professional task";
    return `<button type="button" class="overview-task-btn tone-${tone} ${active ? "active" : ""}" role="option" aria-selected="${active ? "true" : "false"}" data-overview-task="${esc(t.slug)}"><span class="task-idx">${i + 1}</span><b>${esc(t.label || cleanTaskTitle(t.slug))}</b><small>${esc(blurb)}</small></button>`;
  }).join("");
  const meta = taskMetaBySlug(state.overviewTask);
  if (!meta) {
    detail.innerHTML = `<p class="chart-note">Task details unavailable.</p>`;
    return;
  }
  const prompt = (meta.task_prompt || "").trim();
  const tone = taskTypeClass(meta.type);
  const tagline = taskTagline(meta.slug);
  const promptBody = prompt
    ? formatCompareBlocks(prompt)
    : `<p class="compare-md-p">Prompt not available in metadata.</p>`;
  detail.innerHTML = `
    <div class="overview-task-detail-head tone-${tone}">
      <span class="task-type-pill">${esc(meta.type || "Task")}</span>
      <h4>${esc(meta.label || cleanTaskTitle(meta.slug))}</h4>
      ${tagline ? `<p class="task-tagline">${esc(tagline)}</p>` : ""}
      <div class="task-source-row" aria-label="Task source">${taskSourceBadgesHtml(meta.slug)}</div>
    </div>
    <p class="task-prompt-label">Task prompt</p>
    <div class="task-prompt-doc compare-doc compare-doc--deliverable">
      <div class="compare-doc-body">${promptBody}</div>
    </div>`;
  list.querySelectorAll("[data-overview-task]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.overviewTask = btn.dataset.overviewTask;
      renderOverviewTasks();
    });
  });
}

function medalHtml(entry, mode, place) {
  const emoji = place === "gold" ? "🥇" : "🥈";
  const aria = place === "gold" ? "1st place" : "2nd place";
  if (!entry) return `<div class="medal medal-${place}"><span class="medal-rank" aria-label="${aria}">${emoji}</span><span class="medal-model">—</span></div>`;
  return `<div class="medal medal-${place}"><span class="medal-rank" aria-label="${aria}">${emoji}</span><span class="medal-model">${esc(displayModel(entry.model, mode))}</span><span class="medal-mean">mean rank ${entry.mean.toFixed(2)}</span></div>`;
}

function renderOverviewPodium() {
  const el = document.getElementById("overviewPodium");
  if (!el || !state.data) return;
  const aug = taskPodiumStats("augmentation");
  const auto = taskPodiumStats("automation");
  const panel = (title, rows, mode) => `
    <div class="podium-panel">
      <h4>${esc(title)}</h4>
      ${rows.map(r => `
        <div class="podium-row">
          <div class="podium-task">${esc(cleanTaskTitle(r.task))}</div>
          ${medalHtml(r.first, mode, "gold")}
          ${medalHtml(r.second, mode, "silver")}
        </div>`).join("")}
    </div>`;
  el.innerHTML = panel("Augmentation · 1st & 2nd by task", aug, "augmentation")
    + panel("Automation · 1st & 2nd by task", auto, "automation");
}

function renderOverviewHeatmaps() {
  renderReplicateHeatmap(document.getElementById("overviewHeatAug"), "augmentation");
  renderReplicateHeatmap(document.getElementById("overviewHeatAuto"), "automation");
}

function clipCompareRaw(raw, maxChars = 900) {
  const text = String(raw || "").trim();
  if (text.length <= maxChars) return text;
  const slice = text.slice(0, maxChars);
  const breakAt = Math.max(slice.lastIndexOf("\n\n"), slice.lastIndexOf(". "), slice.lastIndexOf("\n"));
  const cut = breakAt > maxChars * 0.55 ? slice.slice(0, breakAt + (slice[breakAt] === "." ? 1 : 0)) : slice;
  return `${cut.trimEnd()}\n\n…`;
}

function teaserPaneLabel(pane, mode) {
  const regime = modeLabels[mode] || mode;
  if (pane === "scaffold") return `${regime} · assistance text`;
  return `${regime} · deliverable`;
}

function teaserExcerptHtml(out, pane, mode) {
  if (!out) return `<p class="qual-empty-state">No output for this selection.</p>`;
  if (pane === "scaffold") {
    if (mode !== "augmentation") {
      return `<p class="qual-empty-state">Assistance text applies only in augmentation mode.</p>`;
    }
    const scaffoldText = assistanceTextOf(out);
    if (!scaffoldText) {
      const msg = isUnaidedBaseline(out)
        ? "Unaided baseline — no assistance text"
        : "No assistance text saved for this model in this run.";
      return `<p class="qual-empty-state">${esc(msg)}</p>`;
    }
    return renderCompareRichText(clipCompareRaw(scaffoldText), { kind: "scaffold" });
  }
  const deliverable = out.output || "No deliverable saved.";
  return renderCompareRichText(clipCompareRaw(deliverable), { kind: "deliverable" });
}

function teaserRunCell(pair) {
  const runId = state.compare.runId || state.runId;
  const bundle = activeData(runId);
  return bundle?.runs?.[`${pair.task}/${pair.mode}`] || null;
}

function applyCompareTeaserPreset(pair = compareTeaserPairs[state.compareTeaserPair]) {
  if (!pair) return;
  state.compare.task = pair.task;
  state.compare.mode = pair.mode;
  state.compare.modelA = pair.modelA;
  state.compare.modelB = pair.modelB;
  state.compare.paneA = pair.paneA;
  state.compare.paneB = pair.paneB;
  state.compare.rubricView = "pair";
  state.compare.rubricJudge = "average";
  if (!state.compare.runId) state.compare.runId = state.runId;
}

function renderTeaserCompactSpine(task, dims, mapA, mapB, labelA, labelB) {
  if (!dims.length) {
    return `<p class="chart-note">No rubric scores found for this selection.</p>`;
  }
  const max = 10;
  const rows = dims.map(dim => {
    const left = mapA.get(dim);
    const right = mapB.get(dim);
    const aBetter = Number.isFinite(left) && Number.isFinite(right) && left > right + 0.05;
    const bBetter = Number.isFinite(left) && Number.isFinite(right) && right > left + 0.05;
    const name = rubricLabels[task]?.[dim] || generalRubricLabels[dim] || dim;
    return `<div class="compare-teaser-spine-row">
      <div class="compare-teaser-spine-dim" title="${esc(name)}">${esc(name)}</div>
      <div class="compare-teaser-spine-cell" title="${esc(labelA)}">
        <div class="bar-track"><div class="bar-fill a" style="width:${Number.isFinite(left) ? left / max * 100 : 0}%"></div></div>
        <span class="compare-teaser-spine-val ${aBetter ? "is-better" : ""}">${Number.isFinite(left) ? left.toFixed(1) : "—"}</span>
      </div>
      <div class="compare-teaser-spine-cell" title="${esc(labelB)}">
        <div class="bar-track"><div class="bar-fill b" style="width:${Number.isFinite(right) ? right / max * 100 : 0}%"></div></div>
        <span class="compare-teaser-spine-val ${bBetter ? "is-better" : ""}">${Number.isFinite(right) ? right.toFixed(1) : "—"}</span>
      </div>
    </div>`;
  }).join("");
  return `
    <div class="compare-teaser-spine">
      <div class="compare-teaser-spine-head">
        <span>Average rubric scores</span>
        <span class="compare-teaser-spine-legend">
          <span><i class="dot a"></i>${esc(labelA)}</span>
          <span><i class="dot b"></i>${esc(labelB)}</span>
        </span>
      </div>
      ${rows}
    </div>`;
}

function renderOverviewCompareTeaser() {
  const root = document.getElementById("overviewCompareTeaser");
  if (!root) return;
  const pair = compareTeaserPairs[state.compareTeaserPair] || compareTeaserPairs[0];
  root.querySelectorAll("[data-teaser-pair]").forEach(btn => {
    const idx = Number(btn.dataset.teaserPair);
    const active = idx === state.compareTeaserPair;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });

  const titleA = document.getElementById("teaserTitleA");
  const titleB = document.getElementById("teaserTitleB");
  const modeA = document.getElementById("teaserModeA");
  const modeB = document.getElementById("teaserModeB");
  const bodyA = document.getElementById("teaserBodyA");
  const bodyB = document.getElementById("teaserBodyB");
  const meanA = document.getElementById("teaserMeanA");
  const meanB = document.getElementById("teaserMeanB");
  const evidence = document.getElementById("teaserEvidence");

  if (titleA) titleA.textContent = displayModel(pair.modelA, pair.mode);
  if (titleB) titleB.textContent = displayModel(pair.modelB, pair.mode);
  if (modeA) modeA.textContent = teaserPaneLabel(pair.paneA, pair.mode);
  if (modeB) modeB.textContent = teaserPaneLabel(pair.paneB, pair.mode);

  if (!state.qualLoaded) {
    // Do not auto-fetch the ~27MB qualitative bundle on every Overview visit —
    // that OOMs Safari on iPhone ("A problem repeatedly occurred…").
    const lowPower = isLowPowerClient();
    if (bodyA) {
      bodyA.innerHTML = lowPower
        ? `<p class="qual-empty-state">Preview available in Compare — tap below to open the full A/B view.</p>`
        : `<p class="qual-empty-state">Evidence loads when this section is on screen…</p>`;
    }
    if (bodyB) {
      bodyB.innerHTML = lowPower
        ? `<p class="qual-empty-state">Open Compare to browse assistance text, rubrics, and rationales.</p>`
        : `<p class="qual-empty-state">Evidence loads when this section is on screen…</p>`;
    }
    if (meanA) meanA.innerHTML = "";
    if (meanB) meanB.innerHTML = "";
    if (evidence) {
      evidence.innerHTML = lowPower
        ? `<p class="chart-note">On phones we skip the large preview download so the page stays stable. Use <b>Open Compare</b> for the full experience.</p>`
        : `<p class="chart-note">Loading rubric spines and judge rationales…</p>`;
    }
    if (!lowPower) scheduleOverviewQualLoad();
    return;
  }

  const cell = teaserRunCell(pair);
  const outputs = cell?.outputs || [];
  const judgments = cell?.judgments || [];
  const outA = outputs.find(o => o.model_label === pair.modelA);
  const outB = outputs.find(o => o.model_label === pair.modelB);

  if (bodyA) bodyA.innerHTML = teaserExcerptHtml(outA, pair.paneA, pair.mode);
  if (bodyB) bodyB.innerHTML = teaserExcerptHtml(outB, pair.paneB, pair.mode);

  const rowsA = outA ? rubricMeansForOutput(outA, judgments, pair.task) : [];
  const rowsB = outB ? rubricMeansForOutput(outB, judgments, pair.task) : [];
  const mapA = new Map(rowsA.map(r => [r.dimension, r.mean]));
  const mapB = new Map(rowsB.map(r => [r.dimension, r.mean]));
  const dims = [...new Set([
    ...Object.keys(rubricLabels[pair.task] || {}),
    ...Object.keys(generalRubricLabels),
    ...rowsA.map(r => r.dimension),
    ...rowsB.map(r => r.dimension),
  ])].filter(dim => mapA.has(dim) || mapB.has(dim));

  const labelA = displayModel(pair.modelA, pair.mode);
  const labelB = displayModel(pair.modelB, pair.mode);
  const avgA = meanRubricScore(rowsA);
  const avgB = meanRubricScore(rowsB);
  if (meanA) {
    meanA.innerHTML = Number.isFinite(avgA)
      ? `<span class="compare-teaser-mean-chip">Mean rubric <b>${avgA.toFixed(1)}</b><small>/ 10</small></span>`
      : "";
  }
  if (meanB) {
    meanB.innerHTML = Number.isFinite(avgB)
      ? `<span class="compare-teaser-mean-chip">Mean rubric <b>${avgB.toFixed(1)}</b><small>/ 10</small></span>`
      : "";
  }

  if (!evidence) return;
  if (!outA || !outB) {
    evidence.innerHTML = `<p class="chart-note">No saved outputs for this preset in the active run.</p>`;
    return;
  }

  const spine = renderTeaserCompactSpine(pair.task, dims, mapA, mapB, labelA, labelB);
  const pairJs = judgments.filter(j => {
    const left = Number(j.left_idx);
    const right = Number(j.right_idx);
    const a = Number(outA.idx);
    const b = Number(outB.idx);
    return (left === a && right === b) || (left === b && right === a);
  });
  const withRationale = pairJs.find(j => rationaleTextOf(j));
  let rationaleHtml = `<p class="chart-note">No direct pairwise rationale for this pair in the active run.</p>`;
  if (withRationale) {
    const aIsLeft = Number(withRationale.left_idx) === Number(outA.idx);
    let winner = "tie / unclear";
    if (withRationale.winner === "option_1") {
      winner = displayModel(aIsLeft ? pair.modelA : pair.modelB, pair.mode);
    } else if (withRationale.winner === "option_2") {
      winner = displayModel(aIsLeft ? pair.modelB : pair.modelA, pair.mode);
    }
    rationaleHtml = `<div class="compare-rationale-card compare-teaser-rationale">
      <div class="compare-rationale-meta"><b>${esc(withRationale.judge_label || judgeDisplay(withRationale.judge_model))}</b> · preferred <b>${esc(winner)}</b></div>
      <p>${esc(rationaleTextOf(withRationale))}</p>
    </div>`;
  }

  evidence.innerHTML = `
    <div class="compare-teaser-evidence-grid">
      ${spine}
      <div class="compare-teaser-rationale-wrap">
        <div class="compare-teaser-spine-head"><span>Judge rationale</span></div>
        ${rationaleHtml}
      </div>
    </div>`;
}

function bindOverviewInteractions() {
  const teaser = document.getElementById("overviewCompareTeaser");
  if (teaser && !teaser.dataset.bound) {
    teaser.dataset.bound = "1";
    teaser.querySelectorAll("[data-teaser-pair]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.compareTeaserPair = Number(btn.dataset.teaserPair) || 0;
        applyCompareTeaserPreset();
        renderOverviewCompareTeaser();
      });
    });
  }
  const openBtn = document.getElementById("overviewOpenCompare");
  if (openBtn && !openBtn.dataset.bound) {
    openBtn.dataset.bound = "1";
    openBtn.addEventListener("click", () => {
      applyCompareTeaserPreset();
      goTab("compare");
    });
  }
}

let overviewQualObserver = null;
function scheduleOverviewQualLoad() {
  if (state.qualLoaded || state.qualLoading || isLowPowerClient()) return;
  const root = document.getElementById("overviewCompareTeaser");
  if (!root) return;
  if (overviewQualObserver || typeof IntersectionObserver === "undefined") {
    ensureQualitativeData().then(() => renderOverviewCompareTeaser()).catch(() => {});
    return;
  }
  overviewQualObserver = new IntersectionObserver(entries => {
    if (!entries.some(e => e.isIntersecting)) return;
    overviewQualObserver.disconnect();
    overviewQualObserver = null;
    ensureQualitativeData().then(() => renderOverviewCompareTeaser()).catch(() => {
      const evidence = document.getElementById("teaserEvidence");
      if (evidence) {
        evidence.innerHTML = `<p class="chart-note">Qualitative bundle failed to load. Open Compare after the page finishes loading.</p>`;
      }
    });
  }, { rootMargin: "200px 0px", threshold: 0.05 });
  overviewQualObserver.observe(root);
}

function renderOverviewLanding() {
  renderHeroStatBand();
  renderOverviewTakeaways();
  renderOverviewTasks();
  renderOverviewPodium();
  renderRoleScatter();
  renderOverviewHeatmaps();
  renderOverviewCompareTeaser();
  bindOverviewInteractions();
}

function renderFindingsSnapshot() {
  const augStats = replicateModelStats("augmentation");
  const autoStats = replicateModelStats("automation");
  const topAugAssistant = augStats.find(d => !isBaselineModel(d.model));
  const topAugOverall = augStats[0];
  const topAuto = autoStats[0];
  const augWinners = taskWinnerStats("augmentation");
  const autoWinners = taskWinnerStats("automation");
  const autoWinnerCount = new Set(autoWinners.map(w => w.model)).size;
  const augWinningAssistants = augWinners.filter(w => !isBaselineModel(w.model));
  const augWinnerCount = new Set(augWinningAssistants.map(w => w.model)).size;
  const plainTaskWins = augWinners.filter(w => isBaselineModel(w.model)).length;
  const autoMean = Number.isFinite(topAuto?.mean) ? topAuto.mean.toFixed(2) : "—";
  const augMean = Number.isFinite(topAugAssistant?.mean) ? topAugAssistant.mean.toFixed(2) : "—";
  const html = `<div class="findings-grid">
    <article class="finding-summary-card finding-card--auto">
      <span class="summary-kicker">Best average automator</span>
      <h4 class="finding-headline">${esc(displayModel(topAuto?.model || "", "automation"))}</h4>
      <div class="finding-metric" aria-label="Mean rank ${autoMean}">
        <span class="finding-metric-num">${esc(autoMean)}</span>
        <span class="finding-metric-label">mean rank<br>across 10 runs · 7 tasks</span>
      </div>
      <p>Automation winners are relatively concentrated.</p>
    </article>
    <article class="finding-summary-card finding-card--aug">
      <span class="summary-kicker">Best average assistant</span>
      <h4 class="finding-headline">${esc(displayModel(topAugAssistant?.model || "", "augmentation"))}</h4>
      <div class="finding-metric" aria-label="Mean rank ${augMean}">
        <span class="finding-metric-num">${esc(augMean)}</span>
        <span class="finding-metric-label">mean rank<br>among assistants</span>
      </div>
      <p>Overall augmentation leader: <strong>${esc(displayModel(topAugOverall?.model || "", "augmentation"))}</strong>.</p>
    </article>
    <article class="finding-summary-card finding-card--spec">
      <span class="summary-kicker">Task specificity</span>
      <h4 class="finding-headline">${augWinnerCount} assistant winners</h4>
      <div class="finding-metric finding-metric--split" aria-label="${augWinnerCount} assistant winners, ${plainTaskWins} unaided wins, ${autoWinnerCount} automation winners">
        <span class="finding-chip"><b>${augWinnerCount}</b><em>aug winners</em></span>
        <span class="finding-chip"><b>${plainTaskWins}</b><em>unaided wins</em></span>
        <span class="finding-chip"><b>${autoWinnerCount}</b><em>auto winners</em></span>
      </div>
      <p>Win at least one augmentation task; automation has ${autoWinnerCount} distinct winners.</p>
    </article>
  </div>
  <div class="winner-block">
    <h3>Augmentation winners by task</h3>
    ${winnerListHtml(augWinners, "augmentation")}
  </div>
  <div class="winner-block">
    <h3>Automation winners by task</h3>
    ${winnerListHtml(autoWinners, "automation")}
  </div>`;
  ["tenRunFindings"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  });
}

function validationRows(check) {
  const rows = [];
  for (const run of runList()) {
    const bundle = activeData(run.id);
    for (const task of taskOrder) {
      const sub = (bundle.by_judge || [])
        .filter(d => d.mode === "automation" && d.task_slug === task && d.judge_model === check.judge && check.models.includes(d.model_label))
        .filter(d => Number.isFinite(Number(d.rank_value)) && Number.isFinite(Number(d.score)))
        .sort((a, b) => Number(a.rank_value) - Number(b.rank_value) || Number(b.score) - Number(a.score) || check.models.indexOf(a.model_label) - check.models.indexOf(b.model_label));
      sub.forEach((d, i) => rows.push({
        run_id: run.id,
        run_label: run.label,
        task: task,
        model: d.model_label,
        score: Number(d.score),
        source_rank: Number(d.rank_value),
        family_rank: i + 1,
      }));
    }
  }
  return rows;
}

function validationOrderStats(check, rows) {
  let wins = 0;
  let ties = 0;
  let total = 0;
  for (const run of runList()) {
    for (const task of taskOrder) {
      const sub = rows.filter(d => d.run_id === run.id && d.task === task);
      const rankByModel = new Map(sub.map(d => [d.model, d.family_rank]));
      for (let i = 0; i < check.models.length; i++) {
        for (let j = i + 1; j < check.models.length; j++) {
          const older = check.models[i];
          const newer = check.models[j];
          if (!rankByModel.has(older) || !rankByModel.has(newer)) continue;
          total += 1;
          const olderRank = rankByModel.get(older);
          const newerRank = rankByModel.get(newer);
          if (newerRank < olderRank) wins += 1;
          else if (newerRank === olderRank) ties += 1;
        }
      }
    }
  }
  return {
    wins,
    ties,
    total,
    agreement: total ? (wins + ties * 0.5) / total : null,
  };
}

function validationModelStats(check, rows) {
  return check.models.map(model => {
    const sub = rows.filter(d => d.model === model);
    const ranks = sub.map(d => d.family_rank);
    const scores = sub.map(d => d.score);
    return {
      model,
      meanRank: ranks.length ? avg(ranks) : null,
      sdRank: ranks.length ? std(ranks) : null,
      meanScore: scores.length ? avg(scores) : null,
      n: sub.length,
    };
  }).filter(d => d.n);
}

function renderValidationHeat(check, rows) {
  const maxRank = check.models.length;
  const byCell = new Map();
  rows.forEach(d => {
    const key = `${d.task}|${d.model}`;
    const arr = byCell.get(key) || [];
    arr.push(d.family_rank);
    byCell.set(key, arr);
  });
  let html = `<table class="heat-table validation-heat"><thead><tr><th>Task</th>${check.models.map(m => `<th>${displayModel(m, "automation")}</th>`).join("")}</tr></thead><tbody>`;
  for (const task of taskOrder) {
    html += `<tr><td>${cleanTaskTitle(task)}</td>`;
    for (const model of check.models) {
      const vals = byCell.get(`${task}|${model}`) || [];
      if (!vals.length) {
        html += `<td class="heat-na">N/A</td>`;
      } else {
        const m = avg(vals);
        const s = std(vals);
        html += `<td style="background:${heatColor(m, maxRank)};color:${m > maxRank * .72 ? "white" : "#172033"}" title="${displayModel(model, "automation")} mean within-family rank across ${vals.length} runs"><b>${m.toFixed(1)}</b><small>±${s.toFixed(1)}</small></td>`;
      }
    }
    html += `</tr>`;
  }
  html += `</tbody></table>`;
  return html;
}

function renderValidationCheck(check) {
  const rows = validationRows(check);
  const order = validationOrderStats(check, rows);
  const models = validationModelStats(check, rows);
  const best = models.slice().sort((a, b) => a.meanRank - b.meanRank || b.meanScore - a.meanScore)[0];
  const modelTable = `<table class="heat-table stability-table validation-models"><thead><tr><th>Reference order</th><th>Model</th><th>Mean family rank</th><th>Rank SD</th><th>Mean win rate</th><th>Cells</th></tr></thead><tbody>${models.map((d, i) => `<tr><td>${i + 1}</td><td>${displayModel(d.model, "automation")}</td><td>${d.meanRank.toFixed(2)}</td><td>${d.sdRank.toFixed(2)}</td><td>${d.meanScore.toFixed(2)}</td><td>${d.n}</td></tr>`).join("")}</tbody></table>`;
  return `<div class="viz-card validation-card">
    <div class="validation-head">
      <div>
        <h3>${esc(check.title)}</h3>
        <p>Judge: <b>${esc(judgeLabels[check.judge] || check.judge)}</b> · Mode: <b>Automation only</b> · Runs: <b>${runList().map(r => r.label).join(", ")}</b></p>
      </div>
      <span class="validation-pill">${esc(check.family)}</span>
    </div>
    <div class="metric-row validation-metrics">
      <div class="metric"><b>${order.agreement === null ? "NA" : `${Math.round(order.agreement * 100)}%`}</b><span>expected-order agreement</span></div>
      <div class="metric"><b>${order.wins}/${order.total}</b><span>strict ordered-pair wins</span></div>
      <div class="metric"><b>${esc(displayModel(best?.model || "", "automation"))}</b><span>best mean family rank</span></div>
      <div class="metric"><b>${esc(displayModel(check.expectedBest, "automation"))}</b><span>expected strongest model</span></div>
    </div>
    <p class="validation-note">${esc(check.note)}</p>
    <div class="validation-cols">
      <div class="validation-table-block">
        <h3>Mean Within-Family Rank By Task</h3>
        ${renderValidationHeat(check, rows)}
      </div>
      <div class="validation-table-block">
        <h3>Model-Level Summary</h3>
        ${modelTable}
      </div>
    </div>
  </div>`;
}

function renderValidation() {
  const el = document.getElementById("validationChecks");
  if (!el) return;
  el.innerHTML = validationChecks.map(renderValidationCheck).join("");
}

function renderProjectStats() {
  const el = document.getElementById("projectStats");
  if (!el) return;
  const totals = totalRunStats();
  const models = new Set(activeData().aggregate.map(d => d.model_label)).size;
  const runCount = runList().length;
  el.innerHTML = [
    [`${runCount}`, runCount === 1 ? "replicate run" : "replicate runs"],
    [`${state.data.tasks.length}`, "tasks"],
    [`${models}`, "candidate conditions"],
    [`${totals.outputs.toLocaleString()}`, "outputs"],
    [`${totals.judgments.toLocaleString()}`, "unique judgments"],
  ].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
}

function runKey() {
  return `${state.task}/${state.mode}`;
}

function currentRun() {
  return activeData().runs[runKey()];
}

function ensureQualPairState() {
  if (!state.qual) state.qual = { judgeFilter: null, pairModel: null };
}

function qualJudgmentHasScores(j) {
  const has = scores => scores && typeof scores === "object"
    && Object.values(scores).some(v => Number.isFinite(Number(v)));
  return has(j?.option_1_scores) && has(j?.option_2_scores);
}

function qualOpponentOf(j, out, byIdx) {
  if (!j || !out) return null;
  const otherIdx = Number(j.left_idx) === Number(out.idx) ? j.right_idx : j.left_idx;
  return byIdx.get(otherIdx) || null;
}

/** Non-empty pairwise judgments for a focal output after leave-family-out. */
function qualValidPairJudgments(out) {
  const run = currentRun();
  const byIdx = new Map((run?.outputs || []).map(o => [o.idx, o]));
  if (!out) return { judgments: [], byIdx };
  const judgments = (run?.judgments || []).filter(j => {
    if (Number(j.left_idx) !== Number(out.idx) && Number(j.right_idx) !== Number(out.idx)) return false;
    if (!j.judge_model || !qualJudgmentHasScores(j)) return false;
    if (isOwnFamily(j.judge_model, out.model_label)) return false;
    const opp = qualOpponentOf(j, out, byIdx);
    if (!opp || opp.model_label === out.model_label) return false;
    if (isOwnFamily(j.judge_model, opp.model_label)) return false;
    return true;
  });
  return { judgments, byIdx };
}

function qualOpponentOptions(out, judgments, byIdx, judgeFilter = null) {
  const seen = new Map();
  judgments.forEach(j => {
    if (judgeFilter && j.judge_model !== judgeFilter) return;
    const opp = qualOpponentOf(j, out, byIdx);
    if (!opp) return;
    if (!seen.has(opp.model_label)) {
      seen.set(opp.model_label, displayModel(opp.model_label, state.mode));
    }
  });
  return [...seen.entries()]
    .map(([model, label]) => ({ model, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function qualJudgeOptionsForOpponent(out, pairModel, judgments, byIdx) {
  const seen = new Map();
  if (!pairModel) return [];
  judgments.forEach(j => {
    const opp = qualOpponentOf(j, out, byIdx);
    if (!opp || opp.model_label !== pairModel) return;
    if (!j.judge_model || seen.has(j.judge_model)) return;
    if (isOwnFamily(j.judge_model, out.model_label)) return;
    if (isOwnFamily(j.judge_model, opp.model_label)) return;
    const scores = judgmentScoresForOutput(j, out);
    if (!scores || !Object.values(scores).some(v => Number.isFinite(Number(v)))) return;
    seen.set(j.judge_model, j.judge_label || judgeDisplay(j.judge_model));
  });
  return [...seen.entries()]
    .map(([model, label]) => ({ model, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function renderQualitative() {
  if (!qualDataReady()) {
    document.getElementById("modelList").innerHTML = "";
    document.getElementById("qualTitle").textContent = "Loading qualitative bundle…";
    document.getElementById("roleStrip").innerHTML = "";
    document.getElementById("qualText").innerHTML = `<p class="qual-loading-inline">Fetching outputs, assistance text, and judge rationales (~28 MB). This loads once per session.</p>`;
    document.getElementById("rationales").innerHTML = "";
    const pairControls = document.getElementById("qualPairControls");
    if (pairControls) pairControls.innerHTML = "";
    const tabDesc = document.getElementById("qualTabDesc");
    if (tabDesc) tabDesc.textContent = qualTabDescriptions[state.textTab] || "";
    return;
  }
  const run = currentRun();
  // Model rail uses panel-aggregate ranks; pairwise panel uses state.qual.judgeFilter chips.
  const ranked = rankOfRanks(state.mode, "aggregate").filter(d => d.task_slug === state.task);
  renderQualQuickPicks(ranked);
  const allowed = new Set(ranked.map(d => d.model_label));
  const outputs = (run?.outputs || []).filter(o => allowed.has(o.model_label));
  if (!state.selectedModel || !outputs.some(o => o.model_label === state.selectedModel)) {
    state.selectedModel = outputs[0]?.model_label;
    ensureQualPairState();
    state.qual.pairModel = null;
    state.qual.judgeFilter = null;
  }
  document.getElementById("modelList").innerHTML = outputs.map(o => {
    const r = ranked.find(d => d.model_label === o.model_label);
    const role = state.mode === "augmentation"
      ? `assistant model: ${displayModel(o.assistant_model || o.model_label, state.mode)} · worker model: ${displayModel(o.worker_model || "gpt-3.5-turbo", state.mode)}`
      : `worker model: ${displayModel(o.model_label, state.mode)}`;
    return `<button class="model-button ${o.model_label === state.selectedModel ? "active" : ""}" data-model="${esc(o.model_label)}"><span>${esc(displayModel(o.model_label, state.mode))}<small class="model-role">${esc(role)}</small></span><span>rank ${r?.display_rank || "?"}</span></button>`;
  }).join("");
  document.querySelectorAll("#modelList .model-button").forEach(b => b.addEventListener("click", () => {
    state.selectedModel = b.dataset.model;
    ensureQualPairState();
    state.qual.pairModel = null;
    state.qual.judgeFilter = null;
    renderAll();
  }));
  const out = outputs.find(o => o.model_label === state.selectedModel) || outputs[0];
  document.getElementById("qualTitle").textContent = out ? `${cleanTaskTitle(state.task)} · ${modeLabels[state.mode]} · ${displayModel(out.model_label, state.mode)}` : "No output";
  const tabDesc = document.getElementById("qualTabDesc");
  if (tabDesc) tabDesc.textContent = qualTabDescriptions[state.textTab] || "";
  const assistant = state.mode === "augmentation" ? displayModel(out?.assistant_model || out?.model_label, state.mode) : "N/A";
  const worker = state.mode === "augmentation" ? displayModel(out?.worker_model || "gpt-3.5-turbo", state.mode) : displayModel(out?.model_label, state.mode);
  const condition = out?.condition || "";
  document.getElementById("roleStrip").innerHTML = out ? [
    ["Mode", modeLabels[state.mode]],
    ["Assistant model", assistant],
    ["Worker model", worker],
    ["Condition", condition.replace(/^scaffold_/i, "Assisted · ").replace(/^automation_/i, "Direct · ")],
  ].map(([k, v]) => `<div class="role-chip"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("") : "";
  const taskObj = state.data.tasks.find(t => t.slug === state.task);
  let sections = [];
  if (state.textTab === "output") {
    sections = [{ label: "Worker model", sublabel: "Produced deliverable", kind: "output",
      body: out?.output || "No output found for this cell.", empty: !out?.output }];
  } else if (state.textTab === "scaffold") {
    const scaffoldText = assistanceTextOf(out);
    const emptyMsg = isUnaidedBaseline(out)
      ? "Unaided baseline — no assistance text"
      : "This direct or unaided-worker condition does not include assistance text.";
    sections = [{ label: "Assistant model", sublabel: "Assistance text passed to the worker model", kind: "assistant",
      body: scaffoldText || emptyMsg, empty: !scaffoldText }];
  } else if (state.textTab === "scaffoldPrompt") {
    sections = [
      { label: "Prompt for Assistance Text", sublabel: "Prompt used to generate the assistant model's assistance text", kind: "assistant",
        body: taskObj?.scaffold_prompt || "No prompt for assistance text found in the dashboard data.", empty: !taskObj?.scaffold_prompt },
      { label: "Worker Model Instruction", sublabel: "How the worker model uses the assistance text", kind: "worker",
        body: taskObj?.worker_instruction || "No worker instruction found in dashboard data.", empty: !taskObj?.worker_instruction },
    ];
  } else if (state.textTab === "prompt") {
    sections = [
      { label: "Task Prompt", sublabel: "The professional task for this cell", kind: "task",
        body: taskObj?.task_prompt || "No task prompt found.", empty: !taskObj?.task_prompt },
      { label: "Prompt for Assistance Text", sublabel: "Used in augmentation to generate the assistant model's guidance", kind: "assistant",
        body: taskObj?.scaffold_prompt || "No prompt for assistance text found in the dashboard data.", empty: !taskObj?.scaffold_prompt },
      { label: "Worker Instruction", sublabel: "How the worker turns inputs into the deliverable", kind: "worker",
        body: taskObj?.worker_instruction || "No worker instruction found in dashboard data.", empty: !taskObj?.worker_instruction },
      { label: "Judge Rubric", sublabel: "Task-specific and general scoring criteria", kind: "evaluator",
        body: taskObj?.rubric || "No rubric found.", empty: !taskObj?.rubric },
    ];
  }
  document.getElementById("qualText").innerHTML = renderQualSections(sections);
  renderRationales(out);
}

function renderRationales(out) {
  ensureQualPairState();
  const controls = document.getElementById("qualPairControls");
  const el = document.getElementById("rationales");
  if (!el) return;
  if (!out) {
    if (controls) controls.innerHTML = "";
    el.innerHTML = "";
    return;
  }

  const { judgments, byIdx } = qualValidPairJudgments(out);
  if (!judgments.length) {
    if (controls) controls.innerHTML = "";
    el.innerHTML = `<div class="qual-empty-state">No leave-family-out eligible pairwise judgments with rubric scores for <b>${esc(displayModel(out.model_label, state.mode))}</b> in this run.</div>`;
    return;
  }

  const opponents = qualOpponentOptions(out, judgments, byIdx, null);
  if (!opponents.some(o => o.model === state.qual.pairModel)) {
    state.qual.pairModel = opponents[0]?.model || null;
  }
  const judgeOpts = qualJudgeOptionsForOpponent(out, state.qual.pairModel, judgments, byIdx);
  if (!judgeOpts.some(j => j.model === state.qual.judgeFilter)) {
    state.qual.judgeFilter = judgeOpts[0]?.model || null;
  }

  const activeJudge = state.qual.judgeFilter;
  const activeOpp = state.qual.pairModel;
  const focalLabel = displayModel(out.model_label, state.mode);
  const oppLabel = displayModel(activeOpp, state.mode);
  const judgeLabel = judgeOpts.find(j => j.model === activeJudge)?.label
    || judgeDisplay(activeJudge);

  if (controls) {
    const judgeButtons = judgeOpts.map(j =>
      `<button type="button" class="compare-judge-chip ${activeJudge === j.model ? "active" : ""}" data-qual-judge="${esc(j.model)}">${esc(j.label)}</button>`
    ).join("");
    const oppButtons = opponents.map(o =>
      `<button type="button" class="compare-judge-chip ${activeOpp === o.model ? "active" : ""}" data-qual-pair="${esc(o.model)}">${esc(o.label)}</button>`
    ).join("");
    controls.innerHTML = `
      <div class="qual-pair-bar" role="tablist" aria-label="Pairwise judge filter">
        <span class="compare-judge-bar-label">Judge</span>
        <div class="compare-judge-chips">${judgeButtons || `<span class="qual-pair-empty">No eligible judges</span>`}</div>
      </div>
      <div class="qual-pair-bar" role="tablist" aria-label="Pairwise opponent model">
        <span class="compare-judge-bar-label">vs</span>
        <div class="compare-judge-chips">${oppButtons || `<span class="qual-pair-empty">No opponents</span>`}</div>
      </div>
      <p class="qual-pair-scope">${esc(judgeLabel)} · ${esc(focalLabel)} vs ${esc(oppLabel)} · leave-family-out only</p>`;
    controls.querySelectorAll("[data-qual-judge]").forEach(btn => {
      btn.addEventListener("click", () => {
        ensureQualPairState();
        state.qual.judgeFilter = btn.dataset.qualJudge;
        renderRationales(out);
      });
    });
    controls.querySelectorAll("[data-qual-pair]").forEach(btn => {
      btn.addEventListener("click", () => {
        ensureQualPairState();
        state.qual.pairModel = btn.dataset.qualPair;
        renderRationales(out);
      });
    });
  }

  const rows = judgments.filter(j => {
    if (j.judge_model !== activeJudge) return false;
    const opp = qualOpponentOf(j, out, byIdx);
    return opp && opp.model_label === activeOpp;
  }).slice(0, 24);

  if (!rows.length) {
    el.innerHTML = `<div class="qual-empty-state">No scored judgments for this judge × opponent pair.</div>`;
    return;
  }

  const dims = [
    ...Object.keys(rubricLabels[state.task] || {}),
    ...Object.keys(generalRubricLabels),
  ];
  const scoreTable = scores => `<div class="score-inline"><table class="mini-score">${dims
    .filter(dim => scores && scores[dim] !== undefined && scores[dim] !== null)
    .map(dim => {
      const score = Number(scores[dim]);
      return `<tr><td><span class="rubric-label" title="${esc(rubricTip(dim))}">${esc(rubricName(dim))}</span></td><td><div class="mini-track"><div class="mini-fill" style="width:${score * 10}%;background:${scoreColor(score)}"></div></div></td><td>${score.toFixed(1)}</td></tr>`;
    })
    .join("")}</table></div>`;

  el.innerHTML = rows.map(j => {
    const left = byIdx.get(j.left_idx);
    const right = byIdx.get(j.right_idx);
    const selected = j.winner === "option_1" ? left : right;
    const leftWinner = selected?.idx === left?.idx;
    const rightWinner = selected?.idx === right?.idx;
    const rationale = rationaleTextOf(j);
    return `<div class="rationale">
      <div class="meta">${esc(j.judge_label || judgeLabel)} · ${esc(displayModel(left?.model_label, state.mode))} vs ${esc(displayModel(right?.model_label, state.mode))}</div>
      <div class="contestants">
        <details class="contestant-detail ${leftWinner ? "winner" : ""}" ${leftWinner ? "open" : ""}>
          <summary><span>Option 1: ${esc(displayModel(left?.model_label, state.mode))}</span><span class="score-chip">avg ${Number(j.option_1_average).toFixed(1)}</span></summary>
          ${scoreTable(j.option_1_scores)}
        </details>
        <details class="contestant-detail ${rightWinner ? "winner" : ""}" ${rightWinner ? "open" : ""}>
          <summary><span>Option 2: ${esc(displayModel(right?.model_label, state.mode))}</span><span class="score-chip">avg ${Number(j.option_2_average).toFixed(1)}</span></summary>
          ${scoreTable(j.option_2_scores)}
        </details>
      </div>
      <p>${esc(rationale || "Rationale missing for this judgment.")}</p>
    </div>`;
  }).join("");
}

function renderModelRoster() {
  const el = document.getElementById("modelRoster");
  if (!el || !state.data?.aggregate) return;
  const models = [...new Set(state.data.aggregate.map(d => d.model_label))].sort();
  const worker = ["GPT-3.5-Turbo", "plain"].filter(m => models.includes(m));
  const candidates = models.filter(m => !worker.includes(m));
  el.innerHTML = [
    { title: "Fixed worker / baselines", items: worker, tone: "baseline" },
    { title: "Focal models under test", items: candidates, tone: "focal" },
  ].map(g => `<div class="model-roster-group model-roster-${g.tone}"><div class="model-roster-label">${esc(g.title)}<span class="model-roster-count">${g.items.length}</span></div><div class="model-roster-chips">${g.items.map(m => `<span class="model-roster-chip">${esc(m)}</span>`).join("")}</div></div>`).join("");
}

function syncPaperCounts() {
  const rc = document.getElementById("replicateRunCount");
  if (rc) rc.textContent = String(runList().length);
}

function populateControls() {
  const runSelect = document.getElementById("runSelect");
  runSelect.innerHTML = runList().map(r => `<option value="${r.id}">${r.label}</option>`).join("");
  runSelect.value = state.runId;
  const modelSet = document.getElementById("modelSet");
  modelSet.innerHTML = Object.entries(state.data.model_sets).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  modelSet.value = state.modelSet;
  document.getElementById("taskSelect").innerHTML = taskOrder.map(t => `<option value="${t}">${cleanTaskTitle(t)}</option>`).join("");
  document.getElementById("taskSelect").value = state.task;
  document.getElementById("modeSelect").value = state.mode;
}

const methodologyDetails = {
  input: {
    title: "Input: seven professional tasks",
    body: "Every condition starts from the same fixed task prompt for each of seven professional tasks: counseling, market trends analysis, weekly menu planning, operations research, tax preparation, travel planning, and tutoring. Prompts, rubrics, and model rosters are versioned in task YAML files, so every model sees identical inputs.",
    action: { label: "Read the exact task prompts", run: () => { state.textTab = "prompt"; syncTextTabs(); goTab("qualitative"); renderAll(); } },
  },
  worker: {
    title: "Worker model: the fixed executor",
    body: "In augmentation, a single low-cost worker — GPT-3.5-Turbo — always produces the deliverable. Because the worker never changes, the only input that varies across augmentation conditions is the assistance text it receives. This isolates the value added by each assistant model. An augmentation run without assistance text serves as the baseline.",
    action: { label: "See worker deliverables", run: () => { setMode("augmentation"); state.textTab = "output"; syncTextTabs(); goTab("qualitative"); renderAll(); } },
  },
  assistant: {
    title: "Assistant model: the model under test",
    body: "Each frontier model writes a piece of process-only assistance text: a 'Three-Phase Workflow' of roughly 200-250 words covering requirements checks, planning, and self-review. The assistance text is validated automatically (no task content leakage, no stubs, and a strict length cap) and regenerated when validation fails. This assistance text — not the assistant model's own answer — is what reaches the worker model.",
    action: { label: "Browse assistance text", run: () => { setMode("augmentation"); state.textTab = "scaffold"; syncTextTabs(); goTab("qualitative"); renderAll(); } },
  },
  automation: {
    title: "Automation regime: the model solves alone",
    body: "Each focal model receives the task prompt directly and produces the deliverable end-to-end. This measures innate capability: no assistance text, no intermediary. These outputs then compete against each other in the automation tournament.",
    action: { label: "View automation task-usage scoreboard", run: () => { setMode("automation"); goTab("rankings"); renderAll(); } },
  },
  augmentation: {
    title: "Augmentation regime: the model guides a fixed worker",
    body: "The focal model acts as an assistant by providing process-focused assistance text to the fixed GPT-3.5-Turbo worker model alongside the client task. The worker model's deliverable is what gets judged, so a model succeeds in this regime by helping its worker perform better — mirroring how AI assistance can augment a human professional.",
    action: { label: "View augmentation task-usage scoreboard", run: () => { setMode("augmentation"); goTab("rankings"); renderAll(); } },
  },
  evaluator: {
    title: "Evaluator panel: blind pairwise judging",
    body: "A panel of LLM judges (GPT-4.1, Claude-Opus-4.8, DeepSeek-V3.1, and Gemini-3.1-Pro) compares outputs two at a time, blind to which model produced them and with option order randomized. Judges never score outputs from their own model family (leave-one-family-out). Each judgment returns a pairwise choice, a short rationale, and per-dimension rubric scores against the task-specific rubric.",
    action: { label: "Browse pairwise rationales", run: () => goTab("qualitative") },
  },
  results: {
    title: "Results aggregation",
    body: "Pairwise wins become win rates per model, task, and regime. Win rates rank models within each task, and per-task ranks roll up into the rank heat maps and role-swap scatter — so every model can be compared as a direct solver versus as an augmenting assistant.",
    action: { label: "View 10-Run Result", run: () => goTab("replicates") },
  },
};

function setMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  state.selectedModel = null;
  state.rubricFocus = null;
}

function syncTextTabs() {
  document.querySelectorAll("[data-texttab]").forEach(x => x.classList.toggle("active", x.dataset.texttab === state.textTab));
}

function goTab(tab) {
  // Judges / Validation are internal diagnostics — keep out of the public nav.
  if (tab === "judges" || tab === "validation") tab = "project";
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(x => {
    const active = x.dataset.tab === tab;
    x.classList.toggle("active", active);
    x.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach(x => x.classList.toggle("active", x.id === tab));
  applyHeaderLayout();
  updateControlBandVisibility();
  renderAll();
  if (needsQualitativeData(tab)) ensureQualitativeData();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateControlBandVisibility() {
  const band = document.getElementById("controlBand");
  if (!band) return;
  const allowed = new Set(controlsByTab[state.tab] || []);
  const showBand = allowed.size > 0;
  band.classList.toggle("hidden", !showBand);
  band.dataset.tab = state.tab || "";
  band.classList.toggle("control-band--qualitative", state.tab === "qualitative");
  band.classList.toggle(
    "control-band--editorial",
    state.tab === "rankings" || state.tab === "overview"
  );
  band.querySelectorAll("[data-control]").forEach(el => {
    const key = el.dataset.control;
    const visible = allowed.has(key);
    el.classList.toggle("hidden", !visible);
    el.classList.toggle("inactive", !visible);
  });
  if (showBand) {
    const cols = allowed.size;
    band.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  }
}

function renderGlossary() {
  const entries = Object.entries(glossary);
  const list = document.getElementById("glossaryList");
  if (list) {
    const preview = entries.slice(0, 5);
    const more = entries.length - preview.length;
    list.innerHTML = preview
      .map(([term, def]) => `<dt>${esc(term)}</dt><dd>${esc(def)}</dd>`)
      .join("") + (more > 0 ? `<dd class="glossary-more-note">+ ${more} more terms — click <b>Open Glossary</b>.</dd>` : "");
  }
  const modalList = document.getElementById("glossaryModalList");
  if (modalList) {
    modalList.innerHTML = entries
      .map(([term, def]) => `<div class="glossary-modal-item"><b>${esc(term)}</b><p>${esc(def)}</p></div>`)
      .join("");
  }
}

function applyTermTooltips(root = document) {
  root.querySelectorAll(".term-inline[data-term]").forEach(el => {
    if (el.dataset.tipApplied) return;
    const term = el.dataset.term;
    const def = glossary[term];
    if (!def) return;
    const label = el.textContent.trim() || term;
    el.innerHTML = `${esc(label)}<button type="button" class="term-info-btn" data-tip="${esc(def)}" data-tip-title="${esc(term)}">i</button>`;
    el.classList.add("term-with-info");
    el.dataset.tipApplied = "1";
  });
  const rankLabel = document.querySelector('[data-control="modelSet"] .label-with-tip');
  if (rankLabel && !rankLabel.dataset.tipApplied) {
    rankLabel.innerHTML = `Model pool<button type="button" class="term-info-btn" data-tip="${esc(glossary["model pool"])}" data-tip-title="Model pool">i</button>`;
    rankLabel.dataset.tipApplied = "1";
  }
  bindFloatingTips(root);
}

function openGlossaryModal() {
  const modal = document.getElementById("glossaryModal");
  if (modal) modal.classList.add("open");
}

function closeGlossaryModal() {
  const modal = document.getElementById("glossaryModal");
  if (modal) modal.classList.remove("open");
}

function bindChrome() {
  if (!document.body.dataset.gotabBound) {
    document.body.dataset.gotabBound = "1";
    document.body.addEventListener("click", e => {
      const btn = e.target.closest("[data-gotab]");
      if (!btn) return;
      e.preventDefault();
      goTab(btn.dataset.gotab);
    });
  }
  document.querySelectorAll("[data-glossary-open]").forEach(btn => {
    btn.addEventListener("click", openGlossaryModal);
  });
  const glossaryClose = document.getElementById("glossaryClose");
  const glossaryModal = document.getElementById("glossaryModal");
  if (glossaryClose) glossaryClose.addEventListener("click", closeGlossaryModal);
  if (glossaryModal) {
    glossaryModal.addEventListener("click", e => {
      if (e.target === glossaryModal) closeGlossaryModal();
    });
  }
  document.addEventListener("click", e => {
    if (!e.target.closest("[data-tip]") && !e.target.closest(".floating-tip")) hideFloatingTip();
  });
  const bibtexBtn = document.getElementById("bibtexBtn");
  const bibtexBlock = document.getElementById("bibtexBlock");
  if (bibtexBtn && bibtexBlock) {
    bibtexBtn.addEventListener("click", async () => {
      const text = bibtexBlock.textContent.trim();
      try {
        await navigator.clipboard.writeText(text);
        bibtexBtn.textContent = "Copied!";
        setTimeout(() => { bibtexBtn.textContent = "BibTeX"; }, 1800);
      } catch {
        bibtexBlock.hidden = !bibtexBlock.hidden;
      }
    });
  }
  renderGlossary();
  applyTermTooltips();
}

function bindMethodology() {
  const detail = document.getElementById("methodDetail");
  if (!detail) return;
  const blocks = document.querySelectorAll(".method-card [data-stage]");
  const show = key => {
    const d = methodologyDetails[key];
    if (!d) return;
    blocks.forEach(b => {
      const active = b.dataset.stage === key;
      b.classList.toggle("active", active);
      b.setAttribute("aria-expanded", active ? "true" : "false");
    });
    detail.innerHTML = `<b>${esc(d.title)}</b><p>${esc(d.body)}</p>${d.action ? `<button class="pill" type="button">${esc(d.action.label)} &#8594;</button>` : ""}`;
    const act = detail.querySelector("button");
    if (act && d.action) act.addEventListener("click", d.action.run);
  };
  blocks.forEach(b => b.addEventListener("click", () => show(b.dataset.stage)));
  show("augmentation");
}

function bind() {
  bindChrome();
  bindLayoutControls();
  bindMethodology();
  bindCompareControls();
  document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => goTab(b.dataset.tab)));
  document.getElementById("runSelect").addEventListener("change", e => {
    state.runId = e.target.value;
    state.selectedModel = null;
    state.rubricFocus = null;
    ensureQualPairState();
    state.qual.pairModel = null;
    state.qual.judgeFilter = null;
    syncActiveRunMirror();
    renderAll();
    if (needsQualitativeData()) ensureQualitativeData();
  });
  document.getElementById("modelSet").addEventListener("change", e => { state.modelSet = e.target.value; renderAll(); });
  document.getElementById("taskSelect").addEventListener("change", e => {
    state.task = e.target.value;
    state.selectedModel = null;
    state.rubricFocus = null;
    ensureQualPairState();
    state.qual.pairModel = null;
    state.qual.judgeFilter = null;
    renderAll();
  });
  document.getElementById("modeSelect").addEventListener("change", e => {
    state.mode = e.target.value;
    state.selectedModel = null;
    state.rubricFocus = null;
    ensureQualPairState();
    state.qual.pairModel = null;
    state.qual.judgeFilter = null;
    renderAll();
  });
  document.querySelectorAll("[data-texttab]").forEach(b => b.addEventListener("click", () => {
    state.textTab = b.dataset.texttab;
    document.querySelectorAll("[data-texttab]").forEach(x => x.classList.toggle("active", x === b));
    renderQualitative();
  }));
}

function compareRunBundle() {
  const runId = state.compare.runId || state.runId;
  return activeData(runId);
}

function compareOutputs() {
  const bundle = compareRunBundle();
  const key = `${state.compare.task}/${state.compare.mode}`;
  return bundle?.runs?.[key]?.outputs || [];
}

function compareJudgments() {
  const bundle = compareRunBundle();
  const key = `${state.compare.task}/${state.compare.mode}`;
  return bundle?.runs?.[key]?.judgments || [];
}

/** Assistance text lives in scaffold_text (Qualitative / qualitative JSON). */
function assistanceTextOf(out) {
  const text = out?.scaffold_text || out?.scaffold || out?.assistance_text || "";
  return typeof text === "string" ? text.trim() : "";
}

/** Judge write-ups use short_rationale in the qualitative bundle. */
function rationaleTextOf(j) {
  const text = j?.short_rationale || j?.rationale || j?.reason || j?.explanation || "";
  return typeof text === "string" ? text.trim() : "";
}

function isUnaidedBaseline(out) {
  if (!out) return false;
  const label = String(out.model_label || out.condition || "").toLowerCase();
  return label === "plain" || label === "gpt-3.5-turbo" || out.condition === "plain";
}

function judgmentScoresForOutput(judgment, output) {
  if (!judgment || !output) return null;
  if (Number(judgment.left_idx) === Number(output.idx)) return judgment.option_1_scores || null;
  if (Number(judgment.right_idx) === Number(output.idx)) return judgment.option_2_scores || null;
  return null;
}

/** Judges that actually scored this output after leave-family-out. */
function judgesWithRubricScoresForOutput(output, judgments) {
  const seen = new Map();
  if (!output) return seen;
  judgments.forEach(j => {
    const key = j.judge_model;
    if (!key || seen.has(key)) return;
    if (isOwnFamily(key, output.model_label)) return;
    const scores = judgmentScoresForOutput(j, output);
    if (!scores || typeof scores !== "object") return;
    const hasNumeric = Object.values(scores).some(v => Number.isFinite(Number(v)));
    if (!hasNumeric) return;
    seen.set(key, j.judge_label || judgeDisplay(key));
  });
  return seen;
}

function rubricMeansForOutput(output, judgments, task, opts = {}) {
  const dims = [
    ...Object.keys(rubricLabels[task] || {}),
    ...Object.keys(generalRubricLabels),
  ];
  const judgeFilter = opts.judgeModel || null;
  const grouped = new Map();
  judgments.forEach(j => {
    if (judgeFilter && j.judge_model !== judgeFilter) return;
    // Leave-family-out: never treat a same-family judge as contributing scores.
    if (!judgeFilter && isOwnFamily(j.judge_model, output.model_label)) return;
    if (judgeFilter && isOwnFamily(judgeFilter, output.model_label)) return;
    const scores = judgmentScoresForOutput(j, output);
    if (!scores) return;
    dims.forEach(dim => {
      if (scores[dim] === undefined || scores[dim] === null) return;
      const arr = grouped.get(dim) || [];
      arr.push(Number(scores[dim]));
      grouped.set(dim, arr);
    });
  });
  return dims
    .filter(d => grouped.has(d))
    .map(d => ({ dimension: d, mean: avg(grouped.get(d)), n: grouped.get(d).length }));
}

function taskAverageRubric(outputs, judgments, task, opts = {}) {
  const byDim = new Map();
  outputs.forEach(out => {
    rubricMeansForOutput(out, judgments, task, opts).forEach(row => {
      const arr = byDim.get(row.dimension) || [];
      arr.push(row.mean);
      byDim.set(row.dimension, arr);
    });
  });
  return [...byDim.entries()].map(([dimension, vals]) => ({ dimension, mean: avg(vals) }));
}

/** Judge chips for Compare: only judges with real scores for both A and B (LOO excluded). */
function compareRubricJudgeOptions(judgments, outA, outB) {
  const forA = judgesWithRubricScoresForOutput(outA, judgments);
  const forB = judgesWithRubricScoresForOutput(outB, judgments);
  // Intersection: a selected judge must be able to populate both sides of the spine/radar.
  const seen = new Map();
  forA.forEach((label, model) => {
    if (!forB.has(model)) return;
    if (outA && isOwnFamily(model, outA.model_label)) return;
    if (outB && isOwnFamily(model, outB.model_label)) return;
    seen.set(model, label);
  });
  // If only one side has outputs yet, fall back to that side's eligible judges.
  if (!seen.size && (forA.size || forB.size)) {
    const src = forA.size ? forA : forB;
    src.forEach((label, model) => seen.set(model, label));
  }
  return [...seen.entries()]
    .map(([model, label]) => ({ model, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function populateCompareControls() {
  const taskEl = document.getElementById("compareTask");
  const runEl = document.getElementById("compareRun");
  const modeEl = document.getElementById("compareMode");
  const aEl = document.getElementById("compareModelA");
  const bEl = document.getElementById("compareModelB");
  const viewEl = document.getElementById("compareRubricView");
  if (!taskEl || !runEl || !aEl || !bEl) return;

  if (!state.compare.runId) state.compare.runId = state.runId;
  if (!taskOrder.includes(state.compare.task)) state.compare.task = state.task;
  if (!state.compare.rubricJudge) state.compare.rubricJudge = "average";

  taskEl.innerHTML = taskOrder.map(t => `<option value="${t}">${cleanTaskTitle(t)}</option>`).join("");
  taskEl.value = state.compare.task;
  runEl.innerHTML = runList().map(r => `<option value="${r.id}">${r.label}</option>`).join("");
  runEl.value = state.compare.runId;
  if (modeEl) modeEl.value = state.compare.mode;
  if (viewEl) viewEl.value = state.compare.rubricView;

  const outputs = compareOutputs();
  const models = [...new Set(outputs.map(o => o.model_label))];
  // Prefer assisted / focal models over the unaided plain baseline so Compare
  // opens on cells that actually have assistance text.
  const preferred = models.filter(m => m !== "plain" && m !== "GPT-3.5-Turbo");
  const pickDefault = (exclude = null) =>
    preferred.find(m => m !== exclude) || models.find(m => m !== exclude) || models[0] || null;
  if (!models.includes(state.compare.modelA)) state.compare.modelA = pickDefault();
  if (!models.includes(state.compare.modelB) || state.compare.modelB === state.compare.modelA) {
    state.compare.modelB = pickDefault(state.compare.modelA);
  }
  aEl.innerHTML = models.map(m => `<option value="${m}">${displayModel(m, state.compare.mode)}</option>`).join("");
  bEl.innerHTML = models.map(m => `<option value="${m}">${displayModel(m, state.compare.mode)}</option>`).join("");
  if (state.compare.modelA) aEl.value = state.compare.modelA;
  if (state.compare.modelB) bEl.value = state.compare.modelB;
}

function comparePairJudgments(outA, outB) {
  if (!outA || !outB) return [];
  return compareJudgments().filter(j => {
    const left = Number(j.left_idx);
    const right = Number(j.right_idx);
    const a = Number(outA.idx);
    const b = Number(outB.idx);
    return (left === a && right === b) || (left === b && right === a);
  });
}

function compareHeadToHeadStats(outA, outB) {
  const pair = comparePairJudgments(outA, outB);
  let winsA = 0;
  let winsB = 0;
  let ties = 0;
  pair.forEach(j => {
    const aIsLeft = Number(j.left_idx) === Number(outA.idx);
    if (j.winner === "option_1") {
      if (aIsLeft) winsA += 1;
      else winsB += 1;
    } else if (j.winner === "option_2") {
      if (aIsLeft) winsB += 1;
      else winsA += 1;
    } else {
      ties += 1;
    }
  });
  return { pair, winsA, winsB, ties, n: pair.length };
}

function meanRubricScore(rows) {
  if (!rows?.length) return null;
  return avg(rows.map(r => r.mean).filter(Number.isFinite));
}

function renderCompareScoreSummary(side, rows, h2h, vsAvg) {
  const el = document.getElementById(side === "a" ? "compareScoreA" : "compareScoreB");
  if (!el) return;
  const mean = meanRubricScore(rows);
  const wins = side === "a" ? h2h.winsA : h2h.winsB;
  const oppWins = side === "a" ? h2h.winsB : h2h.winsA;
  const leadMean = Number.isFinite(mean) && (
    side === "a"
      ? mean >= (meanRubricScore(h2h.rowsB) ?? -Infinity)
      : mean >= (meanRubricScore(h2h.rowsA) ?? -Infinity)
  );
  const leadH2H = h2h.n > 0 && wins > oppWins;

  const chips = [];
  chips.push(`<div class="compare-score-chip ${leadMean && !vsAvg ? "is-lead" : ""}">
    <span class="label">Mean rubric</span>
    <span class="value">${Number.isFinite(mean) ? mean.toFixed(1) : "—"}</span>
    <span class="sub">/ 10 across dims</span>
  </div>`);
  if (!vsAvg) {
    chips.push(`<div class="compare-score-chip ${leadH2H ? "is-lead" : ""}">
      <span class="label">Head-to-head</span>
      <span class="value">${h2h.n ? `${wins}–${oppWins}` : "—"}</span>
      <span class="sub">${h2h.n ? `${h2h.n} judge${h2h.n === 1 ? "" : "s"}` : "no direct pair"}</span>
    </div>`);
  } else {
    chips.push(`<div class="compare-score-chip">
      <span class="label">View</span>
      <span class="value" style="font-size:13px">vs avg</span>
      <span class="sub">task baseline</span>
    </div>`);
  }
  el.innerHTML = chips.join("");
}

/** Light structured formatting for Compare panes (escape first, then mark up). */
function formatCompareInline(escaped) {
  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
}

function splitInlineBulletText(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  // Split paragraphs that use mid-dot / bullet separators into list items.
  const parts = raw.split(/\s*[•·∙]\s+/).map(s => s.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  return parts;
}

function parseCompareTokens(raw) {
  const text = String(raw || "").replace(/\r\n/g, "\n").trim();
  if (!text) return [];
  const tokens = [];
  const fenceParts = text.split(/(```[\s\S]*?```)/g);
  fenceParts.forEach(part => {
    if (!part) return;
    if (part.startsWith("```") && part.endsWith("```")) {
      const inner = part.slice(3, -3).replace(/^\w*\n/, "");
      tokens.push({ type: "code", text: inner.trimEnd() });
      return;
    }
    const lines = part.split("\n");
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i += 1; continue; }

      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        tokens.push({ type: "heading", text: heading[2].trim(), level: heading[1].length });
        i += 1;
        continue;
      }

      const boldTitle = line.match(/^\*\*([^*]+)\*\*\s*$/);
      if (boldTitle) {
        tokens.push({ type: "heading", text: boldTitle[1].trim(), level: 1 });
        i += 1;
        continue;
      }

      const numbered = line.match(/^(\d+)[.)]\s+(.+)$/);
      if (numbered) {
        tokens.push({ type: "section", text: numbered[2].trim(), n: Number(numbered[1]) });
        i += 1;
        continue;
      }

      if (/^[-*•·∙]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^[-*•·∙]\s+/.test(lines[i])) {
          const itemText = lines[i].replace(/^[-*•·∙]\s+/, "").trim();
          const inline = splitInlineBulletText(itemText);
          if (inline && inline.length > 1) items.push(...inline);
          else items.push(itemText);
          i += 1;
        }
        tokens.push({ type: "bullets", items });
        continue;
      }

      const paraLines = [];
      while (i < lines.length && lines[i].trim()
        && !/^\d+[.)]\s+/.test(lines[i])
        && !/^[-*•·∙]\s+/.test(lines[i])
        && !/^#{1,3}\s+/.test(lines[i])
        && !/^\*\*[^*]+\*\*\s*$/.test(lines[i])
        && !(lines[i].startsWith("```"))) {
        paraLines.push(lines[i].trim());
        i += 1;
      }
      if (paraLines.length) {
        const joined = paraLines.join(" ");
        const inline = splitInlineBulletText(joined);
        if (inline) tokens.push({ type: "bullets", items: inline });
        else tokens.push({ type: "para", text: joined });
      }
    }
  });
  return tokens;
}

function renderCompareBodyHtml(tokens) {
  if (!tokens.length) return "";
  const out = [];
  let i = 0;
  let usedTitle = false;

  // Leading title: first heading before any section.
  if (tokens[0]?.type === "heading") {
    out.push(`<h3 class="compare-doc-title">${formatCompareInline(esc(tokens[0].text))}</h3>`);
    usedTitle = true;
    i = 1;
  }

  const flushLoose = (start, end) => {
    const chunk = [];
    for (let k = start; k < end; k += 1) {
      const t = tokens[k];
      if (t.type === "heading") {
        chunk.push(`<h4 class="compare-md-h">${formatCompareInline(esc(t.text))}</h4>`);
      } else if (t.type === "para") {
        chunk.push(`<p class="compare-md-p">${formatCompareInline(esc(t.text))}</p>`);
      } else if (t.type === "bullets") {
        chunk.push(`<ul class="compare-bullets">${t.items.map(it => `<li>${formatCompareInline(esc(it))}</li>`).join("")}</ul>`);
      } else if (t.type === "code") {
        chunk.push(`<pre class="compare-code"><code>${esc(t.text)}</code></pre>`);
      } else if (t.type === "section") {
        // Nested numbered line outside a card — treat as a mini heading + continue
        chunk.push(`<p class="compare-md-p"><strong>${formatCompareInline(esc(t.text))}</strong></p>`);
      }
    }
    return chunk.join("");
  };

  /** Body range for a section token at idx (exclusive end = next section or EOF). */
  const sectionSpan = (idx) => {
    let end = idx + 1;
    while (end < tokens.length && tokens[end].type !== "section") end += 1;
    return end;
  };

  while (i < tokens.length) {
    const t = tokens[i];
    if (t.type === "section") {
      const bodyEnd = sectionSpan(i);
      const bodyHtml = flushLoose(i + 1, bodyEnd);

      // Bare numbered lines (title only, no body) → compact ordered list, not section cards.
      if (!bodyHtml) {
        const items = [];
        while (i < tokens.length && tokens[i].type === "section") {
          const end = sectionSpan(i);
          const body = flushLoose(i + 1, end);
          if (body) break;
          items.push(tokens[i]);
          i = end;
        }
        const start = Number.isFinite(items[0]?.n) ? items[0].n : 1;
        out.push(`<ol class="compare-steps" start="${start}">${items.map(it =>
          `<li>${formatCompareInline(esc(it.text))}</li>`
        ).join("")}</ol>`);
        continue;
      }

      // Numbered step with real body content → section card (no empty-body filler).
      const num = Number.isFinite(t.n) ? t.n : 1;
      const title = t.text;
      i = bodyEnd;
      out.push(`<section class="compare-section">
        <div class="compare-section-head">
          <span class="compare-section-num" aria-hidden="true">${num}</span>
          <h4 class="compare-section-title">${formatCompareInline(esc(title))}</h4>
        </div>
        <div class="compare-section-body">${bodyHtml}</div>
      </section>`);
      continue;
    }

    // Loose content before the first section (or between non-section docs).
    const looseStart = i;
    while (i < tokens.length && tokens[i].type !== "section") i += 1;
    const loose = flushLoose(looseStart, i);
    if (loose) {
      out.push(loose);
    }
  }

  if (!out.length && usedTitle) return out.join("");
  return out.join("") || `<p class="compare-md-p">${formatCompareInline(esc(tokens.map(t => t.text || (t.items || []).join(" ")).join(" ")))}</p>`;
}

function formatCompareBlocks(raw) {
  return renderCompareBodyHtml(parseCompareTokens(raw));
}

function renderCompareRichText(raw, { kind = "deliverable" } = {}) {
  const body = formatCompareBlocks(raw);
  const label = kind === "scaffold" ? "Assistance text" : "Deliverable";
  const kindClass = kind === "scaffold" ? "compare-doc--assist" : "compare-doc--deliverable";
  return `<div class="compare-doc ${kindClass}">
    <div class="compare-doc-label">${label}</div>
    <div class="compare-doc-body">${body}</div>
  </div>`;
}

function renderComparePane(side) {
  const textEl = document.getElementById(side === "a" ? "compareTextA" : "compareTextB");
  const titleEl = document.getElementById(side === "a" ? "compareTitleA" : "compareTitleB");
  if (!textEl || !titleEl) return;
  const model = side === "a" ? state.compare.modelA : state.compare.modelB;
  const pane = side === "a" ? state.compare.paneA : state.compare.paneB;
  const out = compareOutputs().find(o => o.model_label === model);
  titleEl.textContent = model ? displayModel(model, state.compare.mode) : `Model ${side.toUpperCase()}`;

  const tabs = document.querySelector(`.compare-tabs[data-compare-side="${side}"]`);
  if (tabs) {
    tabs.querySelectorAll("[data-compare-pane]").forEach(btn => {
      const active = btn.dataset.comparePane === pane;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  textEl.classList.toggle("is-assist", pane === "scaffold");
  textEl.classList.toggle("is-deliverable", pane !== "scaffold");

  if (!out) {
    textEl.innerHTML = `<p class="qual-empty-state">No output for this selection.</p>`;
    return;
  }
  if (pane === "scaffold") {
    if (state.compare.mode !== "augmentation") {
      textEl.innerHTML = `<p class="qual-empty-state">Assistance text applies only in augmentation mode.</p>`;
      return;
    }
    const scaffoldText = assistanceTextOf(out);
    if (!scaffoldText) {
      const msg = isUnaidedBaseline(out)
        ? "Unaided baseline — no assistance text"
        : "No assistance text saved for this model in this run.";
      textEl.innerHTML = `<p class="qual-empty-state">${esc(msg)}</p>`;
      return;
    }
    textEl.innerHTML = renderCompareRichText(scaffoldText, { kind: "scaffold" });
    return;
  }
  const deliverable = out.output || "No deliverable saved.";
  textEl.innerHTML = renderCompareRichText(deliverable, { kind: "deliverable" });
}

function compareRubricDimName(dim) {
  return rubricLabels[state.compare.task]?.[dim] || generalRubricLabels[dim] || dim;
}

function shortCompareRubricLabel(dim) {
  const full = compareRubricDimName(dim).replace(/^General:\s*/i, "");
  if (full.length <= 24) return full;
  return `${full.slice(0, 22).trimEnd()}…`;
}

/** Absolute radar radius = rubric max. Same for every axis/model (not relative min–max). */
const COMPARE_RADAR_AXIS_MAX = 10;

function compareRadarNorm(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value / COMPARE_RADAR_AXIS_MAX));
}

function buildCompareRadarSvg(axes, series) {
  const n = axes.length;
  if (!n) return `<p class="chart-note">No rubric scores found for this selection.</p>`;

  const size = 420;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 132;
  const levels = 4;
  const angleAt = i => -Math.PI / 2 + (i / n) * Math.PI * 2;
  const pointAt = (i, t) => {
    const a = angleAt(i);
    const r = radius * Math.max(0, Math.min(1, t));
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  const polyPoints = vals => vals.map((t, i) => pointAt(i, t).join(",")).join(" ");

  const rings = Array.from({ length: levels }, (_, li) => {
    const t = (li + 1) / levels;
    const pts = Array.from({ length: n }, (__, i) => pointAt(i, t).join(",")).join(" ");
    return `<polygon class="compare-radar-ring" points="${pts}" />`;
  }).join("");

  const spokes = axes.map((_, i) => {
    const [x, y] = pointAt(i, 1);
    return `<line class="compare-radar-spoke" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" />`;
  }).join("");

  const labels = axes.map((axis, i) => {
    const [x, y] = pointAt(i, 1.22);
    const anchor = Math.abs(x - cx) < 8 ? "middle" : (x > cx ? "start" : "end");
    return `<text class="compare-radar-axis-label" x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle"><title>${esc(axis.full)}</title>${esc(axis.short)}</text>`;
  }).join("");

  const paths = series.map(s => {
    const norms = axes.map(axis => compareRadarNorm(axis.values[s.key]));
    const dash = s.style === "dashed" ? 'stroke-dasharray="8 5"' : (s.style === "dotted" ? 'stroke-dasharray="2 4"' : "");
    const hidden = s.visible ? "" : "is-hidden";
    return `<g class="compare-radar-series ${hidden}" data-radar-series="${esc(s.key)}">
      <polygon class="compare-radar-area" points="${polyPoints(norms)}" fill="${s.color}" />
      <polygon class="compare-radar-line" points="${polyPoints(norms)}" stroke="${s.color}" ${dash} />
      ${norms.map((t, i) => {
        const [x, y] = pointAt(i, t);
        return `<circle class="compare-radar-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="${s.color}" />`;
      }).join("")}
    </g>`;
  }).join("");

  return `<svg class="compare-radar-svg" viewBox="0 0 ${size} ${size}" role="img" aria-label="Rubric score radar chart">${rings}${spokes}${paths}${labels}</svg>`;
}

function renderCompareRadarMarkup(dims, mapA, mapRight, labelA, labelRight, vsAvg) {
  const showA = state.compare.radarShowA !== false;
  const showB = state.compare.radarShowB !== false;
  const seriesMeta = [
    {
      key: "a",
      label: labelA,
      color: "#1f5fbf",
      style: "solid",
      visible: showA,
      pillClass: "a",
    },
    {
      key: "b",
      label: labelRight,
      color: vsAvg ? "#7a8799" : "#c45a1a",
      style: vsAvg ? "dotted" : "dashed",
      visible: showB,
      pillClass: vsAvg ? "avg" : "b",
    },
  ];

  const axes = dims.map(dim => {
    const a = mapA.get(dim);
    const b = mapRight.get(dim);
    return {
      dim,
      full: compareRubricDimName(dim),
      short: shortCompareRubricLabel(dim),
      min: 0,
      max: COMPARE_RADAR_AXIS_MAX,
      values: { a, b },
    };
  }).filter(axis => Number.isFinite(axis.values.a) || Number.isFinite(axis.values.b));

  const legendItems = seriesMeta.map(s => {
    const lineClass = s.style === "dashed" ? "dashed" : (s.style === "dotted" ? "dotted" : "solid");
    return `<button type="button" class="compare-radar-legend-item ${s.visible ? "" : "is-off"}" data-radar-hover="${esc(s.key)}" data-radar-series="${esc(s.key)}">
      <span class="compare-radar-swatch ${lineClass}" style="--swatch:${s.color}"></span>${esc(s.label)}
    </button>`;
  }).join("");

  const pills = seriesMeta.map(s => `
    <button type="button" class="compare-radar-pill ${s.pillClass} ${s.visible ? "active" : ""}" data-radar-toggle="${esc(s.key)}" aria-pressed="${s.visible ? "true" : "false"}">${esc(s.label)}</button>
  `).join("");

  return `
    <div class="compare-radar" id="compareRadar">
      <div class="compare-radar-copy">
        <h3>Rubric fingerprint</h3>
        <p>Selection-rate style radar for rubric scores — same values as the attribute spine.</p>
      </div>
      <div class="compare-radar-toggles" role="group" aria-label="Toggle radar series">${pills}</div>
      <div class="compare-radar-legend">${legendItems}</div>
      <p class="compare-radar-hint">Axes scaled 0–${COMPARE_RADAR_AXIS_MAX} (absolute rubric scores). Hover legend to highlight &amp; see values.</p>
      <div class="compare-radar-stage">
        ${buildCompareRadarSvg(axes, seriesMeta)}
        <div class="compare-radar-values" id="compareRadarValues" hidden></div>
      </div>
    </div>`;
}

function bindCompareRadarInteractions(root, axesPayload, seriesMeta) {
  const radar = root.querySelector("#compareRadar");
  if (!radar) return;
  const valuesEl = radar.querySelector("#compareRadarValues");

  const setHighlight = key => {
    radar.querySelectorAll(".compare-radar-series").forEach(g => {
      const match = !key || g.dataset.radarSeries === key;
      g.classList.toggle("is-dimmed", Boolean(key) && !match);
      g.classList.toggle("is-focus", Boolean(key) && match);
    });
    radar.querySelectorAll(".compare-radar-legend-item").forEach(item => {
      const match = !key || item.dataset.radarSeries === key;
      item.classList.toggle("is-dimmed", Boolean(key) && !match);
      item.classList.toggle("is-focus", Boolean(key) && match);
    });
    if (!valuesEl) return;
    if (!key) {
      valuesEl.hidden = true;
      valuesEl.innerHTML = "";
      return;
    }
    const series = seriesMeta.find(s => s.key === key);
    if (!series || !series.visible) {
      valuesEl.hidden = true;
      return;
    }
    const rows = axesPayload.map(axis => {
      const v = axis.values[key];
      return `<div><span>${esc(axis.short)}</span><b>${Number.isFinite(v) ? v.toFixed(2) : "—"}</b></div>`;
    }).join("");
    valuesEl.hidden = false;
    valuesEl.innerHTML = `<div class="compare-radar-values-title" style="color:${series.color}">${esc(series.label)}</div>${rows}`;
  };

  radar.querySelectorAll("[data-radar-toggle]").forEach(btn => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.radarToggle;
      if (key === "a") {
        if (state.compare.radarShowA && !state.compare.radarShowB) return;
        state.compare.radarShowA = !state.compare.radarShowA;
      } else {
        if (state.compare.radarShowB && !state.compare.radarShowA) return;
        state.compare.radarShowB = !state.compare.radarShowB;
      }
      renderCompareRubric();
    });
  });

  radar.querySelectorAll("[data-radar-hover]").forEach(item => {
    item.addEventListener("mouseenter", () => setHighlight(item.dataset.radarHover));
    item.addEventListener("mouseleave", () => setHighlight(null));
    item.addEventListener("focus", () => setHighlight(item.dataset.radarHover));
    item.addEventListener("blur", () => setHighlight(null));
  });

  radar.querySelectorAll(".compare-radar-series").forEach(g => {
    g.addEventListener("mouseenter", () => setHighlight(g.dataset.radarSeries));
    g.addEventListener("mouseleave", () => setHighlight(null));
  });
}

function renderCompareRubric() {
  const el = document.getElementById("compareRubric");
  if (!el) return;
  const outputs = compareOutputs();
  const judgments = compareJudgments();
  const outA = outputs.find(o => o.model_label === state.compare.modelA);
  const outB = outputs.find(o => o.model_label === state.compare.modelB);
  if (!outA || !outB) {
    el.innerHTML = `<p class="chart-note">Pick two models with saved outputs to compare rubric scores.</p>`;
    renderCompareScoreSummary("a", [], { winsA: 0, winsB: 0, n: 0, rowsA: [], rowsB: [] }, false);
    renderCompareScoreSummary("b", [], { winsA: 0, winsB: 0, n: 0, rowsA: [], rowsB: [] }, false);
    return;
  }

  const judgeOpts = compareRubricJudgeOptions(judgments, outA, outB);
  if (state.compare.rubricJudge !== "average"
    && !judgeOpts.some(j => j.model === state.compare.rubricJudge)) {
    state.compare.rubricJudge = "average";
  }
  const judgeModel = state.compare.rubricJudge === "average" ? null : state.compare.rubricJudge;
  // Guard: never ask a leave-family-out judge for scores on this pair.
  if (judgeModel
    && (isOwnFamily(judgeModel, outA.model_label) || isOwnFamily(judgeModel, outB.model_label))) {
    state.compare.rubricJudge = "average";
  }
  const activeJudge = state.compare.rubricJudge === "average" ? null : state.compare.rubricJudge;
  const rubricOpts = activeJudge ? { judgeModel: activeJudge } : {};
  const judgeLabel = activeJudge
    ? (judgeOpts.find(j => j.model === activeJudge)?.label || judgeDisplay(activeJudge))
    : "Average";

  const rowsA = rubricMeansForOutput(outA, judgments, state.compare.task, rubricOpts);
  const rowsB = rubricMeansForOutput(outB, judgments, state.compare.task, rubricOpts);
  const avgRows = taskAverageRubric(outputs, judgments, state.compare.task, rubricOpts);
  const dims = [...new Set([
    ...Object.keys(rubricLabels[state.compare.task] || {}),
    ...Object.keys(generalRubricLabels),
    ...rowsA, ...rowsB, ...avgRows,
  ].map(r => (typeof r === "string" ? r : r.dimension)))];
  const mapA = new Map(rowsA.map(r => [r.dimension, r.mean]));
  const mapB = new Map(rowsB.map(r => [r.dimension, r.mean]));
  const mapAvg = new Map(avgRows.map(r => [r.dimension, r.mean]));
  const vsAvg = state.compare.rubricView === "avg";
  const mapRight = vsAvg ? mapAvg : mapB;
  const labelA = displayModel(state.compare.modelA, state.compare.mode);
  const labelB = displayModel(state.compare.modelB, state.compare.mode);
  const labelRight = vsAvg ? "Task average" : labelB;
  const h2h = compareHeadToHeadStats(outA, outB);
  h2h.rowsA = rowsA;
  h2h.rowsB = rowsB;
  renderCompareScoreSummary("a", rowsA, h2h, vsAvg);
  renderCompareScoreSummary("b", rowsB, h2h, vsAvg);

  const rightColor = vsAvg ? "var(--compare-avg)" : "var(--compare-b)";
  const max = 10;
  const scopeNote = activeJudge
    ? (vsAvg
      ? `${judgeLabel} scores · A vs task average under this judge`
      : `${judgeLabel} scores · A vs B`)
    : (vsAvg
      ? "Average across leave-family-out eligible judges · A vs task average"
      : "Average across leave-family-out eligible judges · A vs B");

  const rows = dims.map(dim => {
    const left = mapA.get(dim);
    const right = mapRight.get(dim);
    const aBetter = Number.isFinite(left) && Number.isFinite(right) && left > right + 0.05;
    const bBetter = Number.isFinite(left) && Number.isFinite(right) && right > left + 0.05;
    return `<div class="compare-rubric-row">
      <div class="compare-rubric-dim">${esc(compareRubricDimName(dim))}</div>
      <div class="compare-rubric-cell" data-side="A · ${esc(labelA)}" title="${esc(labelA)}">
        <div class="bar-track"><div class="bar-fill" style="width:${Number.isFinite(left) ? left / max * 100 : 0}%;background:var(--compare-a)"></div></div>
        <span class="compare-rubric-val ${aBetter ? "is-better" : ""}">${Number.isFinite(left) ? left.toFixed(1) : "—"}</span>
      </div>
      <div class="compare-rubric-cell" data-side="${vsAvg ? "Task avg" : `B · ${esc(labelB)}`}" title="${vsAvg ? "Task average" : esc(labelB)}">
        <div class="bar-track"><div class="bar-fill" style="width:${Number.isFinite(right) ? right / max * 100 : 0}%;background:${rightColor}"></div></div>
        <span class="compare-rubric-val ${bBetter ? "is-better" : ""}">${Number.isFinite(right) ? right.toFixed(1) : "—"}</span>
      </div>
    </div>`;
  }).join("");

  const judgeButtons = [
    `<button type="button" class="compare-judge-chip ${state.compare.rubricJudge === "average" ? "active" : ""}" data-compare-judge="average">Average</button>`,
    ...judgeOpts.map(j => `<button type="button" class="compare-judge-chip ${state.compare.rubricJudge === j.model ? "active" : ""}" data-compare-judge="${esc(j.model)}">${esc(j.label)}</button>`),
  ].join("");

  const radarHtml = renderCompareRadarMarkup(dims, mapA, mapRight, labelA, labelRight, vsAvg);
  const seriesMeta = [
    { key: "a", label: labelA, color: "#1f5fbf", visible: state.compare.radarShowA !== false },
    {
      key: "b",
      label: labelRight,
      color: vsAvg ? "#7a8799" : "#c45a1a",
      visible: state.compare.radarShowB !== false,
    },
  ];
  const axesPayload = dims.map(dim => ({
    short: shortCompareRubricLabel(dim),
    values: { a: mapA.get(dim), b: mapRight.get(dim) },
  })).filter(axis => Number.isFinite(axis.values.a) || Number.isFinite(axis.values.b));

  el.innerHTML = `
    <div class="section-heading compact">
      <h2>Rubric attributes</h2>
      <p>${esc(labelA)} vs ${vsAvg ? "task average" : esc(labelB)} · ${esc(cleanTaskTitle(state.compare.task))} · ${esc(modeLabels[state.compare.mode])}</p>
    </div>
    <div class="compare-judge-bar" role="tablist" aria-label="Rubric judge filter">
      <span class="compare-judge-bar-label">Scores from</span>
      <div class="compare-judge-chips">${judgeButtons}</div>
    </div>
    <div class="compare-rubric-viz">
      ${radarHtml}
      <div class="compare-rubric-spine">
        <div class="compare-rubric-legend">
          <span><span class="dot a"></span>${esc(labelA)}</span>
          <span><span class="dot b" ${vsAvg ? 'style="background:var(--compare-avg)"' : ""}></span>${esc(labelRight)}</span>
          <span class="compare-rubric-scope">${esc(scopeNote)}</span>
        </div>
        <div class="compare-rubric-head" aria-hidden="true">
          <span class="col-dim">Dimension</span>
          <span class="col-a">A</span>
          <span class="col-b">${vsAvg ? "Avg" : "B"}</span>
        </div>
        ${rows || `<p class="chart-note">No rubric scores found for this selection.</p>`}
      </div>
    </div>`;

  el.querySelectorAll("[data-compare-judge]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.compare.rubricJudge = btn.dataset.compareJudge;
      renderCompareRubric();
    });
  });
  bindCompareRadarInteractions(el, axesPayload, seriesMeta);
}

function renderCompareRationales() {
  const el = document.getElementById("compareRationales");
  if (!el) return;
  const outputs = compareOutputs();
  const outA = outputs.find(o => o.model_label === state.compare.modelA);
  const outB = outputs.find(o => o.model_label === state.compare.modelB);
  if (!outA || !outB) {
    el.innerHTML = `<p class="chart-note">No head-to-head judgments for this pair.</p>`;
    return;
  }
  const pair = comparePairJudgments(outA, outB);
  if (!pair.length) {
    el.innerHTML = `<p class="chart-note">No direct pairwise matchup between these two models in this run. Try another run, or browse Qualitative for related rationales.</p>`;
    return;
  }
  el.innerHTML = pair.map(j => {
    const aIsLeft = Number(j.left_idx) === Number(outA.idx);
    // Judgments store winner as "option_1" / "option_2" (same as Qualitative).
    let winner = "tie / unclear";
    if (j.winner === "option_1") {
      winner = displayModel(aIsLeft ? state.compare.modelA : state.compare.modelB, state.compare.mode);
    } else if (j.winner === "option_2") {
      winner = displayModel(aIsLeft ? state.compare.modelB : state.compare.modelA, state.compare.mode);
    }
    const rationale = rationaleTextOf(j);
    return `<div class="compare-rationale-card">
      <div class="compare-rationale-meta"><b>${esc(j.judge_label || judgeDisplay(j.judge_model))}</b> · preferred <b>${esc(winner)}</b></div>
      <p>${esc(rationale || "Rationale missing for this judgment.")}</p>
    </div>`;
  }).join("");
}

function renderCompare() {
  const panel = document.getElementById("compare");
  if (!panel) return;
  const loading = document.getElementById("compareLoadingNote");
  populateCompareControls();
  if (!state.qualLoaded) {
    if (loading) loading.classList.remove("hidden");
    ensureQualitativeData().then(() => renderCompare());
    return;
  }
  const run = compareRunBundle()?.runs?.[`${state.compare.task}/${state.compare.mode}`];
  if (!run?.outputs?.length) {
    if (loading) {
      loading.classList.remove("hidden");
      loading.textContent = "No outputs found for this task, role, and run.";
    }
    document.getElementById("compareRubric").innerHTML = "";
    document.getElementById("compareTextA").innerHTML = "";
    document.getElementById("compareTextB").innerHTML = "";
    document.getElementById("compareRationales").innerHTML = "";
    const scoreA = document.getElementById("compareScoreA");
    const scoreB = document.getElementById("compareScoreB");
    if (scoreA) scoreA.innerHTML = "";
    if (scoreB) scoreB.innerHTML = "";
    return;
  }
  if (loading) loading.classList.add("hidden");
  renderCompareRubric();
  renderComparePane("a");
  renderComparePane("b");
  renderCompareRationales();
}

function bindCompareControls() {
  const bind = (id, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", fn);
  };
  bind("compareTask", e => { state.compare.task = e.target.value; renderCompare(); });
  // Keep Model A/B when still present in the new mode; populateCompareControls falls back only if missing.
  bind("compareMode", e => { state.compare.mode = e.target.value; renderCompare(); });
  bind("compareRun", e => { state.compare.runId = e.target.value; renderCompare(); });
  bind("compareModelA", e => { state.compare.modelA = e.target.value; renderCompare(); });
  bind("compareModelB", e => { state.compare.modelB = e.target.value; renderCompare(); });
  bind("compareRubricView", e => { state.compare.rubricView = e.target.value; renderCompare(); });
  document.querySelectorAll(".compare-tabs").forEach(group => {
    group.querySelectorAll("[data-compare-pane]").forEach(btn => {
      btn.addEventListener("click", () => {
        const side = group.dataset.compareSide;
        group.querySelectorAll(".compare-seg, .pill").forEach(p => {
          p.classList.remove("active");
          p.setAttribute("aria-selected", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        if (side === "a") state.compare.paneA = btn.dataset.comparePane;
        else state.compare.paneB = btn.dataset.comparePane;
        renderComparePane(side);
      });
    });
  });
}

function renderAll() {
  try {
    populateControls();
    syncPaperCounts();
    updateControlBandVisibility();
    renderModelRoster();
    renderProjectStats();
    // Only paint the active public tab (+ Overview always, since it's the landing shell).
    const tab = state.tab || "project";
    if (tab === "project") renderOverviewLanding();
    if (tab === "replicates") {
      renderFindingsSnapshot();
      renderReplicateSummary();
    }
    if (tab === "overview") renderHeatmaps();
    if (tab === "rankings") renderRankings();
    if (tab === "qualitative") renderQualitative();
    if (tab === "compare") renderCompare();
    // Judges / Validation stay out of the public render path (hidden diagnostics).
    applyTermTooltips();
  } catch (err) {
    console.error("Dashboard render failed:", err);
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) overlay.classList.add("hidden");
    document.body.classList.remove("loading");
    const msg = document.createElement("div");
    msg.className = "render-error-banner";
    msg.innerHTML = `<b>Dashboard render error:</b> ${esc(String(err))}`;
    document.body.prepend(msg);
  }
}

initAmbientCanvas();
document.body.classList.add("loading");
fetch("dashboard-meta.json")
  .then(r => {
    if (!r.ok) throw new Error(`Failed to load dashboard-meta.json (${r.status})`);
    return r.json();
  })
  .then(data => {
    state.data = data;
    state.runId = data.meta.default_run_id || data.meta.run_id;
    syncActiveRunMirror();
    populateControls();
    bind();
    renderAll();
    document.body.classList.remove("loading");
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) overlay.classList.add("hidden");
  })
  .catch(err => {
    document.body.classList.remove("loading");
    document.body.innerHTML = `<main><div class="viz-card"><h1>Dashboard data failed to load</h1><pre>${err}</pre></div></main>`;
  });
