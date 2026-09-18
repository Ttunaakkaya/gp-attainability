"use strict";

// This dashboard renders simulation artifacts only. It never synthesizes runs.
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const METHODS = {
  sweep: { name: "Systematic sweep", short: "Sweep", color: "#81ade5", explanation: "Systematic sweep follows a fixed coverage route. It offers a simple geometric baseline independent of the GP information map." },
  greedy: { name: "Greedy information", short: "Greedy", color: "#f6a18a", explanation: "Greedy information plans from expected measurements and follows that schedule open-loop. Lost observations and tracking deviations can separate the forecast from reality." },
  adaptive: { name: "Adaptive greedy", short: "B2 adaptive greedy", color: "#5bd8bb", explanation: "B2: adaptive greedy re-plans its next targets every epoch from the current GP and the robots’ actual positions. It is not Bellman-DP and not the proposed policy P; an improvement is not guaranteed." },
  dp: { name: "Periodic DP", short: "B3 periodic DP", color: "#b7a0f5", explanation: "B3: periodic Bellman-DP selects a bounded, timed waypoint plan from the current belief and actual positions. Every update shares the same mission deadline. Forecasts are geometric and conditional on expected observations; this is not the proposed budget-recovery policy or a controller rollout." },
  p: { name: "Execution-aware", short: "P execution-aware", color: "#e8c25a", explanation: "P: the proposed M4 policy scores each bounded candidate at the positions a nominal controller rollout says the fleet would reach, keeps the plan already in force unless another candidate beats it by an explicit margin, and extends every candidate to the common deadline with an executable hold so all are scored over the same remaining epochs. The mission-end value is an upper candidate from an executable plan, not an attainability floor; implementing P is not evidence that P beats B3." },
};
// Both planners record timed plans; only P adds decision, budget and target risk.
const PLANNERS = ["dp", "p"];
const SCENARIOS = {
  nominal: "Sensor noise remains; measurements arrive without added loss or tracking drift.",
  dropout: "Some planned observations are lost. Only measurements that arrive update the GP.",
  drift: "Robots deviate from their requested motion. The GP uses actual measurement positions.",
  combined: "Missed measurements and route deviations challenge the original plan.",
};
const ROBOT_COLORS = ["#ffdf94", "#c3a5f0", "#8de8e5", "#ffa29c"];
// Plain-language names for recorded decision codes; the raw codes stay in the data export.
const TRIGGERS = {
  initial: "the mission start",
  periodic_sampling_epoch: "a scheduled sampling epoch",
  missed_measurement: "a lost measurement",
  execution_deviation: "a robot drifting off its reference path",
  control_intervention: "the safety controller changing a command",
};
const REASONS = {
  no_plan_in_force: "there was no plan yet",
  plan_retention_disabled_by_ablation: "plan retention is switched off",
  retained_plan_shares_no_remaining_epoch: "the plan in force had no epochs left",
  retained_plan_no_longer_executable_from_here: "the plan in force was no longer executable from where the robots actually are",
  candidate_improves_mission_forecast_beyond_switch_margin: "a new candidate lowers the mission-end forecast by more than the switch margin",
  retained_plan_within_switch_margin_of_the_best_candidate: "no candidate beats the plan in force by more than the switch margin",
};
const MODEL_LABELS = { holonomic: "Holonomic", usv: "USV v0", usv_curvature: "Turn-constrained USV" };
const PALETTES = {
  field: [[20, 42, 67], [34, 88, 111], [49, 138, 137], [118, 180, 151], [225, 225, 166]],
  std: [[29, 36, 66], [71, 62, 110], [135, 86, 130], [205, 126, 135], [255, 219, 175]],
  error: [[22, 45, 57], [53, 86, 103], [136, 114, 117], [213, 144, 127], [255, 224, 177]],
};
const state = { comparison: null, method: "adaptive", frameIndex: 0, motionIndex: 0, layer: "mean", playing: false, busy: false, playTime: 0, lastAnimation: 0, heat: {}, scales: null, videoAvailable: false, compare: false, showcase: null, showcases: [] };
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const number = (value, digits = 3) => finite(value) ? value.toFixed(digits) : "—";
const clock = (seconds) => `${Math.floor(Math.max(0, seconds || 0) / 60)}:${String(Math.floor(Math.max(0, seconds || 0) % 60)).padStart(2, "0")}`;
const currentRun = () => state.comparison?.runs.find((run) => run.method === state.method) || state.comparison?.runs[0];
const currentFrame = () => currentRun()?.frames?.[state.frameIndex];
const motionRecords = (run = currentRun()) => run?.motion?.length ? run.motion : run?.frames || [];
const currentMotion = () => motionRecords()[state.motionIndex] || currentFrame();
const lastFrame = (run) => run.frames?.[run.frames.length - 1] || {};
const methodInfo = (method) => METHODS[method] || { name: method, short: method, color: "#91a3af", explanation: "Simulation output." };
const runStatus = (run) => run?.status || (run?.failure ? "failed" : "completed");
const isCompleted = (run) => Boolean(run) && runStatus(run) === "completed";
const controllerMode = (run) => run?.config?.controller || "filter";
const completedTime = (run) => run?.summary?.completion_time_s ?? lastFrame(run || {}).time_s;
const scientific = (value) => finite(value) ? value.toExponential(2) : "—";
const currentControl = (run) => {
  const motion = currentMotion();
  return Number.isInteger(motion?.control_event_index)
    ? run?.controls?.[motion.control_event_index] || {}
    : motion?.control || {};
};
const currentPlan = (run = currentRun()) => {
  const eligible = (run?.plans || []).filter((plan) => finite(plan.generated_at_s) && plan.generated_at_s <= state.playTime + 1e-8);
  // The arriving motion may still reference the previous plan at a replan epoch.
  return eligible.reduce((latest, plan) => !latest || plan.generated_at_s >= latest.generated_at_s ? plan : latest, null);
};

const indexAt = (items, time) => { const next = items.findIndex((item) => item.time_s > time + 1e-8); return next < 0 ? Math.max(0, items.length - 1) : Math.max(0, next - 1); };
const runOf = (method) => state.comparison?.runs.find((run) => run.method === method);
const frameAt = (run) => run?.frames?.[indexAt(run.frames || [], state.playTime)];
const motionAt = (run) => { const records = motionRecords(run); return records[indexAt(records, state.playTime)] || frameAt(run); };
const comparePair = () => [runOf("dp"), runOf("p")];
const canCompare = () => comparePair().every(Boolean);
const comparing = () => state.compare && canCompare();

function decisionSentence(plan) {
  const decision = plan?.decision;
  if (!decision) return "";
  const action = { initial: "set its first plan", replaced: "replaced its plan", retained: "kept its plan" }[decision.action] || "recorded a decision";
  return `At ${number(plan.generated_at_s, 1)} s, ${TRIGGERS[decision.trigger] || "a recorded event"} led P to check; it ${action} because ${REASONS[decision.reason] || "of its recorded rule"}.`;
}

function targetSentence(plan) {
  const risk = plan?.target_risk || {}, ending = plan?.mission_end_forecast || {};
  if (!finite(risk.target_mean_variance)) return "No fixed mission target was set for this run.";
  const reach = risk.status === "forecast_attainable_in_candidate_set";
  return `Fixed target ${number(risk.target_mean_variance, 4)}; P's mission-end forecast is ${number(ending.mean_variance ?? risk.selected_mission_end_mean_variance, 4)}. ${reach ? "Some candidate's forecast reaches the target." : "No candidate in this bounded search reaches it; that is not a proof that the target is impossible."}`;
}

function setReplayTime(time) {
  const records = motionRecords(), frames = currentRun()?.frames || [];
  state.playTime = Math.max(0, Math.min(time || 0, records[records.length - 1]?.time_s || 0));
  const atOrBefore = (items) => { const next = items.findIndex((item) => item.time_s > state.playTime + 1e-8); return next < 0 ? Math.max(0, items.length - 1) : Math.max(0, next - 1); };
  state.motionIndex = atOrBefore(records); state.frameIndex = atOrBefore(frames);
}

function updateScenarioHelp() {
  const scenario = $("#scenario").value, model = $("#model").value;
  const disturbance = ["drift", "combined"].includes(scenario) ? model === "usv" ? " USV drift perturbs yaw rate (rad/s)." : model === "usv_curvature" ? " Drift is a yaw-rate tracking error on the commanded curvature." : " Drift perturbs velocity (m/s)." : "";
  $("#scenario-description").textContent = (SCENARIOS[scenario] || "") + disturbance;
}

function updateControllerHelp() {
  const model = $("#model").value, usv = model !== "holonomic", turnInPlace = model === "usv", selector = $("#controller");
  const reverted = usv && selector.value === "qp";
  selector.querySelector('[value="qp"]').disabled = usv;
  if (reverted) selector.value = "filter";
  $("#controller-help").textContent = turnInPlace
    ? `${reverted ? "Switched to geometric filter. " : ""}Velocity QP is holonomic-only; the v0 USV keeps its turn-limited filter.`
    : usv
      ? `${reverted ? "Switched to the arc filter. " : ""}Velocity QP is holonomic-only. The turn-constrained USV uses a certified arc filter: every robot keeps a private loiter circle and 2 m separation.`
      : selector.value === "qp"
        ? "M1 QP filters the speed-capped tracking command before motion. Solver diagnostics are recorded; this is not unknown post-control wind."
        : "Backtracking scales requested motion to meet the simulated constraints. Legacy runs use this geometric filter.";
  for (const id of ["#include-dp", "#include-p"]) { $(id).disabled = turnInPlace; if (turnInPlace) $(id).checked = false; }
  $("#dp-help").textContent = turnInPlace
    ? "The v0 USV turns on the spot and has no heading-aware planner. Choose the turn-constrained USV for B3."
    : usv
      ? "Adds B3: a motion-primitive Bellman tree over arcs the boat can actually fly (M7)."
      : "Adds B3: a bounded Bellman planner with timed targets; keeps your selected controller.";
  $("#p-help").textContent = turnInPlace
    ? "The v0 USV has no heading-aware planner. Choose the turn-constrained USV for P."
    : usv
      ? "Adds P: its rollout replays each candidate through the USV guidance and arc filter. Expect about a minute per mission."
      : "Adds P: controller rollout, retained-plan check and remaining-budget scoring. The rollout makes this run noticeably slower than B3.";
  $("#target").disabled = !$("#include-p").checked;
}

function status(message, kind = "ready") {
  $("#status-text").textContent = message;
  $("#run-status .status-dot").className = `status-dot${kind === "busy" ? " busy-dot" : kind === "idle" ? " muted-dot" : ""}`;
}

function updateGPHelp() {
  const sparse = $("#gp-backend").value === "sogp";
  $("#sogp-settings").hidden = !sparse;
  $("#sogp-max-basis").disabled = !sparse;
  $("#sogp-novelty-tolerance").disabled = !sparse;
  $("#gp-help").textContent = sparse
    ? "Bounded online dictionary; approximation depends on admission, pruning and update order. All selected methods use the same backend and capacity."
    : "Exact reference retains all received observations. The same backend is used by every selected method.";
}

function setPlaying(playing) {
  state.playing = playing && Boolean(currentRun()?.frames?.length);
  $("#play-button").setAttribute("aria-label", state.playing ? "Pause mission replay" : "Play mission replay");
  $("#play-icon").innerHTML = state.playing ? '<path d="M5 4h3v12H5Zm7 0h3v12h-3Z"/>' : '<path d="M6 3.5 16 10 6 16.5Z"/>';
  state.lastAnimation = 0;
  if (state.playing) requestAnimationFrame(animate);
}

function animate(timestamp) {
  if (!state.playing) return;
  const previousIndex = state.motionIndex;
  if (state.lastAnimation) setReplayTime(state.playTime + Math.min((timestamp - state.lastAnimation) / 1000, 0.25) * Number($("#playback-speed").value));
  state.lastAnimation = timestamp;
  const records = motionRecords();
  if (state.motionIndex !== previousIndex) renderReplay();
  if (state.playTime >= records[records.length - 1].time_s) { renderReplay(); setPlaying(false); return; }
  requestAnimationFrame(animate);
}

function selectMethod(method) {
  if (state.comparison && !state.comparison.runs.some((run) => run.method === method)) return;
  const time = state.playTime;
  state.method = method;
  setReplayTime(time);
  $$(".method-card").forEach((card) => { const selected = card.dataset.method === method; card.classList.toggle("selected", selected); card.setAttribute("aria-pressed", String(selected)); });
  $("#method-explanation").textContent = methodInfo(method).explanation;
  $(".explainer-rule").style.borderColor = methodInfo(method).color;
  renderReplay();
}

function canvasContext(canvas) {
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(1, bounds.width), height = Math.max(1, bounds.height);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(width * dpr), pixelHeight = Math.round(height * dpr);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);
  return { context, width, height };
}

function interpolateColor(palette, fraction) {
  const position = Math.max(0, Math.min(1, fraction)) * (palette.length - 1);
  const index = Math.min(palette.length - 2, Math.floor(position)), ratio = position - index;
  return palette[index].map((value, channel) => Math.round(value * (1 - ratio) + palette[index + 1][channel] * ratio));
}

function computeScales() {
  let fieldMin = Infinity, fieldMax = -Infinity, maxStd = 0, maxError = 0;
  for (const run of state.comparison.runs) {
    for (const row of run.field?.truth || []) for (const value of row) if (finite(value)) { fieldMin = Math.min(fieldMin, value); fieldMax = Math.max(fieldMax, value); }
    for (const frame of run.frames || []) {
      for (const row of frame.std || []) for (const value of row) if (finite(value)) maxStd = Math.max(maxStd, value);
      for (const row of frame.error || []) for (const value of row) if (finite(value)) maxError = Math.max(maxError, Math.abs(value));
    }
  }
  state.scales = { field: [finite(fieldMin) ? fieldMin : 0, finite(fieldMax) && fieldMax > fieldMin ? fieldMax : 1], std: [0, maxStd || 1], error: [0, maxError || 1] };
}

function heatmap(matrix, minValue, maxValue, palette, key, slot = "a") {
  const cached = state.heat[slot];
  if (cached?.key === key) return cached.image;
  const offscreen = document.createElement("canvas");
  offscreen.width = matrix[0]?.length || 1; offscreen.height = matrix.length || 1;
  const context = offscreen.getContext("2d"), pixels = context.createImageData(offscreen.width, offscreen.height);
  for (let y = 0; y < offscreen.height; y++) for (let x = 0; x < offscreen.width; x++) {
    const value = matrix[y]?.[x], index = ((offscreen.height - 1 - y) * offscreen.width + x) * 4;
    const color = finite(value) ? interpolateColor(palette, (value - minValue) / (maxValue - minValue || 1)) : [22, 35, 46];
    pixels.data[index] = color[0]; pixels.data[index + 1] = color[1]; pixels.data[index + 2] = color[2]; pixels.data[index + 3] = 255;
  }
  context.putImageData(pixels, 0, 0);
  state.heat[slot] = { key, image: offscreen };
  return offscreen;
}

// Rebuild a USV plan as the arcs the boat flies: each epoch is one recorded primitive
// (full or half budget, turning fully left, straight or right, or a stop) when the
// recorded pose reproduces the target exactly; otherwise the segment stays straight.
function arcEnd(point, heading, length, curvature) {
  const half = 0.5 * curvature * length, sinc = Math.abs(half) < 1e-12 ? 1 : Math.sin(half) / half, chord = length * sinc, direction = heading + half;
  return [point[0] + chord * Math.cos(direction), point[1] + chord * Math.sin(direction)];
}

function planPolyline(plan, run, robot, anchor) {
  const waypoints = (plan.targets_by_epoch || []).map((targets) => targets?.[robot]);
  if (run.config?.model !== "usv_curvature" || !anchor) return [anchor, ...waypoints];
  const config = run.config, radius = config.max_speed / config.max_turn_rate;
  let heading = plan.start_headings?.[robot];
  if (!finite(heading)) {
    const pose = motionRecords(run).filter((item) => item.time_s <= plan.generated_at_s + 1e-8).pop();
    const position = pose?.positions?.[robot];
    heading = position && Math.hypot(position[0] - anchor[0], position[1] - anchor[1]) < 1e-6 ? pose.headings?.[robot] : undefined;
  }
  const points = [anchor];
  let position = anchor, previous = plan.generated_at_s;
  waypoints.forEach((target, epoch) => {
    const time = plan.sample_times_s?.[epoch];
    if (!target) return;
    let matched = null;
    if (finite(heading) && finite(radius) && finite(time)) {
      const budget = config.max_speed * (time - previous);
      for (const fraction of [1, 0.5, 0]) for (const turn of [1, 0, -1]) {
        const length = fraction * budget, curvature = turn / radius, end = arcEnd(position, heading, length, curvature);
        if (!matched && Math.hypot(end[0] - target[0], end[1] - target[1]) < 1e-3) matched = { length, curvature };
      }
    }
    if (matched) {
      for (let step = 1; step <= 12; step++) points.push(arcEnd(position, heading, matched.length * step / 12, matched.curvature));
      heading += matched.curvature * matched.length;
    } else { points.push(target); heading = undefined; }
    position = target; previous = time;
  });
  return points;
}

function drawMap(canvas = $("#map-canvas"), run = currentRun(), slot = "a") {
  const { context: ctx, width, height } = canvasContext(canvas);
  const frame = frameAt(run), motion = motionAt(run);
  if (!run || !frame) {
    ctx.strokeStyle = "#21344080"; ctx.lineWidth = 0.5;
    for (let x = 15; x < width; x += 28) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    for (let y = 15; y < height; y += 28) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    return;
  }
  const field = run.field || {}, xs = field.x || [], ys = field.y || [];
  if (!xs.length || !ys.length) return;
  const xmin = xs[0], xmax = xs[xs.length - 1], ymin = ys[0], ymax = ys[ys.length - 1];
  const margin = { top: 46, bottom: 34, left: 41, right: 34 };
  const scale = Math.min((width - margin.left - margin.right) / (xmax - xmin || 1), (height - margin.top - margin.bottom) / (ymax - ymin || 1));
  const plotWidth = (xmax - xmin) * scale, plotHeight = (ymax - ymin) * scale;
  const left = (width - plotWidth) / 2, top = margin.top + (height - margin.top - margin.bottom - plotHeight) / 2;
  const transform = (point) => [left + (point[0] - xmin) * scale, top + plotHeight - (point[1] - ymin) * scale];
  const paletteName = ["truth", "mean"].includes(state.layer) ? "field" : state.layer;
  const palette = PALETTES[paletteName], [minValue, maxValue] = state.scales[paletteName];
  const matrix = state.layer === "truth" ? field.truth : state.layer === "error" ? frame.error?.map((row) => row.map((value) => Math.abs(value))) : frame[state.layer];
  if (matrix?.length) {
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(heatmap(matrix, minValue, maxValue, palette, `${run.method}-${state.layer}-${frame.time_s}`, slot), left, top, plotWidth, plotHeight);
  }
  ctx.strokeStyle = "#b7d4d021"; ctx.lineWidth = 0.6;
  for (let tick = 0; tick <= 4; tick++) {
    const x = left + tick * plotWidth / 4, y = top + tick * plotHeight / 4;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + plotHeight); ctx.moveTo(left, y); ctx.lineTo(left + plotWidth, y); ctx.stroke();
  }
  ctx.strokeStyle = "#74909570"; ctx.strokeRect(left, top, plotWidth, plotHeight);
  ctx.fillStyle = "#8096a4"; ctx.font = '9px "Segoe UI", sans-serif'; ctx.textAlign = "center";
  for (let tick = 0; tick <= 4; tick++) { const value = xmin + tick * (xmax - xmin) / 4; ctx.fillText(number(value, Math.abs(value) < 5 && value % 1 ? 1 : 0), left + tick * plotWidth / 4, top + plotHeight + 15); }
  ctx.fillStyle = "#658192"; ctx.font = '8px "Segoe UI", sans-serif'; ctx.fillText("x / m", left + plotWidth / 2, top + plotHeight + 28);
  ctx.textAlign = "right"; ctx.fillStyle = "#8096a4"; ctx.font = '9px "Segoe UI", sans-serif';
  for (let tick = 0; tick <= 4; tick++) { const value = ymin + tick * (ymax - ymin) / 4; ctx.fillText(number(value, Math.abs(value) < 5 && value % 1 ? 1 : 0), left - 8, top + plotHeight - tick * plotHeight / 4 + 3); }
  ctx.save(); ctx.translate(left - 29, top + plotHeight / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.fillStyle = "#658192"; ctx.font = '8px "Segoe UI", sans-serif'; ctx.fillText("y / m", 0, 0); ctx.restore();
  ctx.save(); ctx.beginPath(); ctx.rect(left - 1, top - 1, plotWidth + 2, plotHeight + 2); ctx.clip();
  const robotCount = motion.positions?.length || run.initial_positions?.length || 0;
  const history = motionRecords(run).filter((item) => item.time_s <= state.playTime + 1e-8);
  const plan = PLANNERS.includes(run.method) ? currentPlan(run) : null;
  for (let robot = 0; robot < robotCount; robot++) {
    const color = ROBOT_COLORS[robot % ROBOT_COLORS.length];
    if ($("#show-planned").checked && run.motion?.length) {
      if (PLANNERS.includes(run.method)) {
        // A plan overlay originates at its recorded generation pose, never at
        // the current pose or from a plan created after the replay cursor.
        const anchor = plan?.start_positions || plan?.starts || [...history].reverse().find((item) => item.time_s <= (plan?.generated_at_s ?? -1) + 1e-8)?.positions;
        if (plan && anchor) {
          const waypoints = (plan.targets_by_epoch || []).map((targets) => targets?.[robot]);
          drawPath(ctx, planPolyline(plan, run, robot, anchor[robot]), transform, `${color}95`, 1.1, [2, 5]);
          // P scores each sample where its controller rollout says the robot will be.
          if (run.method === "p") (plan.predicted_sample_sites || []).forEach((sites, epoch) => {
            const site = sites?.[robot], target = waypoints[epoch], time = plan.sample_times_s?.[epoch];
            if (!site || !finite(time) || time <= state.playTime + 1e-8) return;
            const [x, y] = transform(site);
            if (target) { const [tx, ty] = transform(target); if (Math.hypot(tx - x, ty - y) > 3) { ctx.strokeStyle = `${color}80`; ctx.lineWidth = 0.9; ctx.setLineDash([1, 3]); ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(x, y); ctx.stroke(); ctx.setLineDash([]); } }
            ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(x, y, 3.4, 0, Math.PI * 2); ctx.stroke();
          });
          const markerGroups = new Map();
          waypoints.forEach((target, epoch) => {
            const time = plan.sample_times_s?.[epoch];
            if (!target || !finite(time) || time <= state.playTime + 1e-8) return;
            const key = JSON.stringify(target), group = markerGroups.get(key) || { target, times: [] };
            group.times.push(time); markerGroups.set(key, group);
          });
          for (const { target, times } of markerGroups.values()) {
            const [x, y] = transform(target);
            ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.strokeRect(x - 2.5, y - 2.5, 5, 5);
            ctx.fillStyle = color; ctx.font = '8px "Segoe UI", sans-serif'; ctx.textAlign = "left";
            ctx.fillText(`${times.map((time) => number(time, time % 1 ? 1 : 0)).join("/")}s`, x + 5, y - 4);
          }
        }
      } else if (run.method === "adaptive") {
        // Each rolling forecast starts at the actual replanning pose. Joining
        // adjacent forecasts would invent a segment that was never planned.
        for (let epoch = 0; epoch < run.frames.length; epoch++) {
          const anchor = run.frames[epoch];
          if (anchor.time_s > state.playTime + 1e-8) break;
          const end = run.frames[epoch + 1]?.time_s ?? Infinity;
          const segment = history.filter((item) => item.time_s > anchor.time_s + 1e-8 && item.time_s <= end + 1e-8);
          drawPath(ctx, [anchor.positions?.[robot], ...segment.map((item) => item.planned_positions?.[robot])], transform, `${color}85`, 1.0, [4, 4]);
        }
      } else drawPath(ctx, [run.initial_positions?.[robot], ...history.map((item) => item.planned_positions?.[robot])], transform, `${color}85`, 1.0, [4, 4]);
    }
    drawPath(ctx, [run.initial_positions?.[robot], ...history.map((item) => item.positions?.[robot])], transform, color, 1.8, []);
  }
  for (const sample of run.samples || []) {
    if (sample.time_s > state.playTime + 1e-8 || !sample.actual_position) continue;
    const [x, y] = transform(sample.actual_position);
    if (sample.received) { ctx.beginPath(); ctx.arc(x, y, 2.1, 0, Math.PI * 2); ctx.fillStyle = ROBOT_COLORS[sample.robot_id % ROBOT_COLORS.length] + "c0"; ctx.fill(); ctx.strokeStyle = "#0e1c2980"; ctx.lineWidth = 0.6; ctx.stroke(); }
    else { ctx.strokeStyle = "#ffb298d0"; ctx.lineWidth = 1.1; ctx.beginPath(); ctx.moveTo(x - 2.8, y - 2.8); ctx.lineTo(x + 2.8, y + 2.8); ctx.moveTo(x + 2.8, y - 2.8); ctx.lineTo(x - 2.8, y + 2.8); ctx.stroke(); }
  }
  for (let robot = 0; robot < robotCount; robot++) {
    const target = motion.targets?.[robot];
    if (target) { const [x, y] = transform(target); ctx.strokeStyle = ROBOT_COLORS[robot % ROBOT_COLORS.length] + "90"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 5, y); ctx.closePath(); ctx.stroke(); }
  }
  ctx.restore();
  const step = Number.isInteger(motion?.control_event_index) ? run.controls?.[motion.control_event_index] : null;
  for (let robot = 0; robot < robotCount; robot++) {
    if (!motion.positions[robot]) continue;
    const [x, y] = transform(motion.positions[robot]), color = ROBOT_COLORS[robot % ROBOT_COLORS.length];
    if (step?.loitering?.[robot]) { ctx.strokeStyle = "#d8e6e3b0"; ctx.lineWidth = 1; ctx.setLineDash([2, 2]); ctx.beginPath(); ctx.arc(x, y, 12.5, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); }
    ctx.save(); ctx.translate(x, y); ctx.rotate(-(motion.headings?.[robot] || 0)); ctx.shadowColor = "#06101f"; ctx.shadowBlur = 8;
    ctx.fillStyle = "#16222c"; ctx.strokeStyle = color; ctx.lineWidth = 1.8; ctx.beginPath(); ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.shadowBlur = 0;
    ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(5, 0); ctx.lineTo(-3, -3); ctx.lineTo(-1.5, 0); ctx.lineTo(-3, 3); ctx.closePath(); ctx.fill(); ctx.restore();
    ctx.font = '600 8px "Segoe UI", sans-serif'; ctx.textAlign = "center"; ctx.fillStyle = "#0e1a24d9"; ctx.fillRect(x - 10, y - 23, 20, 11); ctx.fillStyle = color; ctx.fillText(`R${robot + 1}`, x, y - 15);
  }
  $("#scale-gradient").style.background = `linear-gradient(to right, ${palette.map((color) => `rgb(${color.join(",")})`).join(",")})`;
  $("#scale-min").textContent = number(minValue, 2); $("#scale-max").textContent = number(maxValue, 2);
  $("#scale-title").textContent = ({ truth: "TRUE FIELD VALUE", mean: "GP MEAN VALUE", std: "LATENT STD · σ", error: "ABSOLUTE ERROR" })[state.layer];
}

function drawPath(ctx, points, transform, color, lineWidth, dash) {
  ctx.beginPath(); let started = false;
  for (const point of points) { if (!point || !finite(point[0]) || !finite(point[1])) { started = false; continue; } const [x, y] = transform(point); if (started) ctx.lineTo(x, y); else { ctx.moveTo(x, y); started = true; } }
  ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
}

function drawChart(canvas, series, selectedTime, { compact = false } = {}) {
  const { context: ctx, width, height } = canvasContext(canvas);
  const left = 40, right = 12, top = 10, bottom = 27, plotWidth = Math.max(1, width - left - right), plotHeight = Math.max(1, height - top - bottom);
  const points = series.flatMap((item) => item.points.filter((point) => finite(point[0]) && finite(point[1])));
  if (!points.length) { ctx.fillStyle = "#65808f"; ctx.font = '11px "Segoe UI", sans-serif'; ctx.textAlign = "center"; ctx.fillText("Awaiting simulation output", width / 2, height / 2); return; }
  const maxTime = Math.max(1, ...points.map((point) => point[0]));
  const maxValue = Math.max(1e-8, ...points.map((point) => point[1])) * 1.08;
  const transform = (point) => [left + point[0] / maxTime * plotWidth, top + plotHeight * (1 - point[1] / maxValue)];
  const yTicks = compact ? 2 : 3;
  ctx.font = '9px "Segoe UI", sans-serif'; ctx.lineWidth = 0.6;
  for (let tick = 0; tick <= yTicks; tick++) {
    const y = top + plotHeight * tick / yTicks, value = maxValue * (1 - tick / yTicks);
    ctx.strokeStyle = "#2d414d"; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
    ctx.fillStyle = "#8298a5"; ctx.textAlign = "right"; ctx.fillText(value < .01 && value > 0 ? value.toExponential(0) : value.toFixed(maxValue < 1 ? 2 : 1), left - 8, y + 3);
  }
  for (let tick = 0; tick <= 4; tick++) { const x = left + plotWidth * tick / 4; ctx.fillStyle = "#8298a5"; ctx.textAlign = "center"; ctx.fillText(`${Math.round(maxTime * tick / 4)}${tick === 4 ? " s" : ""}`, x, height - 8); }
  ctx.save(); ctx.beginPath(); ctx.rect(left, top, plotWidth, plotHeight + 1); ctx.clip();
  for (const item of series) drawPath(ctx, item.points, transform, item.color, item.dash ? 1.4 : 1.8, item.dash || []);
  if (finite(selectedTime)) {
    const x = left + selectedTime / maxTime * plotWidth;
    ctx.strokeStyle = "#b1cbd255"; ctx.lineWidth = 1; ctx.setLineDash([2, 4]); ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + plotHeight); ctx.stroke(); ctx.setLineDash([]);
    for (const item of series) { const point = [...item.points].reverse().find((itemPoint) => finite(itemPoint[1]) && itemPoint[0] <= selectedTime); if (!point) continue; const [px, py] = transform(point); ctx.beginPath(); ctx.arc(px, py, 2.5, 0, Math.PI * 2); ctx.fillStyle = item.color; ctx.fill(); }
  }
  ctx.restore();
}

function renderCharts() {
  const runs = state.comparison?.runs || [], frame = currentFrame(), run = currentRun();
  const series = (metric) => runs.map((item) => ({ color: methodInfo(item.method).color, points: (item.frames || []).map((point) => [point.time_s, point[metric]]) }));
  drawChart($("#rmse-chart"), series("rmse"), state.playTime);
  drawChart($("#variance-chart"), series("mean_variance"), state.playTime);
  $("#rmse-chart").setAttribute("aria-label", `Map root mean squared error across mission time for ${runs.length} recorded methods`);
  $("#variance-chart").setAttribute("aria-label", `Mean latent posterior variance across mission time for ${runs.length} recorded methods`);
  drawChart($("#gap-chart"), run ? [
    { color: "#5bd8bb", points: run.frames.map((point) => [point.time_s, point.mean_variance]) },
    { color: "#b1bccd", points: run.frames.map((point) => [point.time_s, point.planned_mean_variance]), dash: [5, 4] },
  ] : [], state.playTime, { compact: true });
  const gap = finite(frame?.mean_variance) && finite(frame?.planned_mean_variance) ? frame.mean_variance - frame.planned_mean_variance : null;
  $("#gap-value").textContent = finite(gap) ? `${gap >= 0 ? "+" : ""}${number(gap, 3)} Δ` : "—";
  $("#gap-value").title = "Observed minus planned mean latent variance at the selected time";
}

function renderReplay() {
  const run = currentRun(), frame = currentFrame(), available = Boolean(frame);
  $("#empty-map").hidden = available; $("#map-live-meta").hidden = !available; $("#scale-legend").hidden = !available;
  $("#replay-slider").disabled = !available; $("#play-button").disabled = !available;
  $("#replay-slider").max = Math.max(0, motionRecords(run).length - 1); $("#replay-slider").value = state.motionIndex;
  $("#current-time").textContent = clock(state.playTime); $("#total-time").textContent = clock(lastFrame(run || {}).time_s);
  $("#map-method-label").textContent = methodInfo(state.method).name.toUpperCase(); $("#map-method-label").style.color = methodInfo(state.method).color;
  $("#frame-observations").textContent = `${frame?.samples_received ?? 0} OBSERVATIONS`;
  $("#map-unit").textContent = ({ truth: "KNOWN SIMULATION FIELD", mean: "LATENT FIELD ESTIMATE", std: "LATENT STANDARD DEVIATION", error: "AGAINST SIMULATION TRUTH" })[state.layer];
  drawMaps(); renderCharts(); renderControl(); renderGP(); renderPlan();
}

function drawMaps() {
  const compare = comparing(), [left, right] = comparePair();
  $("#map-stage").classList.toggle("compare", compare);
  $("#map-canvas-b").hidden = !compare;
  $("#pane-label-a").hidden = !compare; $("#pane-label-b").hidden = !compare;
  if (compare) $("#map-live-meta").hidden = true;
  $("#compare-toggle").disabled = !canCompare();
  $("#compare-toggle").setAttribute("aria-pressed", String(compare));
  $("#compare-toggle").title = canCompare() ? "Replay B3 and P side by side on the same world" : "Needs a recording with both B3 and P";
  const shown = compare ? [left, right] : [currentRun()].filter(Boolean);
  $("#legend-rollout").hidden = !shown.some((run) => run.method === "p" && run.plans?.some((plan) => plan.predicted_sample_sites));
  $("#legend-loiter").hidden = !shown.some((run) => run.config?.model === "usv_curvature");
  if (!compare) { drawMap($("#map-canvas"), currentRun(), "a"); $("#decision-strip").hidden = true; return; }
  drawMap($("#map-canvas"), left, "a"); drawMap($("#map-canvas-b"), right, "b");
  for (const [id, run] of [["#pane-label-a", left], ["#pane-label-b", right]]) {
    $(id).textContent = `${methodInfo(run.method).short.toUpperCase()} · ${frameAt(run)?.samples_received ?? 0} OBSERVATIONS`;
    $(id).style.color = methodInfo(run.method).color;
  }
  const b3 = currentPlan(left), managed = currentPlan(right);
  $("#decision-strip").hidden = false;
  $("#decision-a").replaceChildren(Object.assign(document.createElement("strong"), { textContent: "B3 · " }), b3 ? `plan ${b3.plan_version} made at ${number(b3.generated_at_s, 1)} s. B3 re-plans on schedule every 5 s and always replaces the previous plan.` : "no plan yet at this time.");
  $("#decision-b").replaceChildren(Object.assign(document.createElement("strong"), { textContent: "P · " }), managed ? `${decisionSentence(managed)} ${targetSentence(managed)}` : "no decision yet at this time.");
}

function renderGP() {
  // Never substitute final-run counters at an earlier cursor or invent evidence
  // for legacy bundles that did not record per-frame GP telemetry.
  const run = currentRun(), telemetry = currentFrame()?.gp_telemetry;
  $("#gp-panel").hidden = run?.config?.gp_backend !== "sogp" || !telemetry;
  if ($("#gp-panel").hidden) return;
  $("#gp-badge").textContent = `${telemetry.dictionary_size ?? "—"} / ${telemetry.max_basis ?? "—"} BASIS`;
  const forecast = run.scope?.forecast;
  $("#gp-scope").textContent = `Dictionary pruning is an approximation and can change uncertainty. ${["sweep", "greedy"].includes(run.method) ? "This offline baseline uses a fixed exact-prior nominal-route surrogate for its forecast, not future SOGP evolution." : "Planning conditions a frozen approximate posterior; it does not predict future dictionary admission or label-dependent pruning."} Numeric state excludes replay logs and planning workspaces.${forecast ? ` Logged forecast scope: ${forecast}.` : ""}`;
  const list = $("#gp-diagnostics"); list.replaceChildren();
  const diagnostics = [
    ["Assimilated observations", String(telemetry.observation_count ?? "—")],
    ["Admitted / projected updates", `${telemetry.admitted_count ?? "—"} / ${telemetry.projected_count ?? "—"}`],
    ["Pruned basis points", String(telemetry.pruned_count ?? "—")],
    ["Numeric GP state", finite(telemetry.state_nbytes) ? `${number(telemetry.state_nbytes / 1024, 1)} KiB` : "—"],
    ["Dictionary capacity", String(telemetry.max_basis ?? "—")],
    ["Recorded through", `${number(currentFrame()?.time_s, 1)} s`],
  ];
  for (const [label, value] of diagnostics) { const item = document.createElement("div"), term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = label; description.textContent = value; item.append(term, description); list.append(item); }
}

function renderPlan() {
  const run = currentRun(), planner = PLANNERS.includes(run?.method), plan = planner ? currentPlan(run) : null;
  $("#plan-panel").hidden = !planner;
  if (!planner) return;
  $("#plan-subtitle").textContent = `Plan known at the replay cursor · ${methodInfo(run.method).short}`;
  $("#plan-badge").textContent = plan ? `PLAN ${plan.plan_version ?? plan.plan_id}` : "NO PLAN AT CURSOR";
  const list = $("#plan-diagnostics"); list.replaceChildren();
  if (!plan) {
    $("#plan-scope").textContent = "No timed plan had been recorded at this replay time. A later plan is never substituted.";
    $("#legend-hold").hidden = true; $("#legend-target").hidden = true;
    drawChart($("#plan-forecast-chart"), [], state.playTime, { compact: true });
    return;
  }
  const times = (plan.sample_times_s || []).filter(finite), forecast = plan.forecast || [];
  const selected = plan.selected_candidate_id ?? plan.selected_candidate;
  const candidate = typeof selected === "object" && selected !== null ? selected.candidate_id ?? selected.name ?? JSON.stringify(selected) : selected;
  const diagnostics = [
    ["Plan ID / version", `${plan.plan_id ?? "—"} / ${plan.plan_version ?? "—"}`],
    ["Generated at", `${number(plan.generated_at_s, 1)} s`],
    ["Common mission end", `${number(plan.mission_end_s, 1)} s`],
    ["Remaining time · at cursor", `${finite(plan.mission_end_s) ? number(Math.max(0, plan.mission_end_s - state.playTime), 1) : "—"} s`],
    ["Horizon end / epochs", `${times.length ? number(Math.max(...times), 1) : number(plan.generated_at_s, 1)} s / ${times.length}`],
    ["Candidates / selected", `${plan.candidates?.length ?? "—"} / ${candidate ?? "—"}`],
    ["Belief observations · at planning", String(plan.belief_observation_count ?? "—")],
    ["Scheduled sample times", times.length ? times.map((time) => `${number(time, 1)} s`).join(" · ") : "No future measurement epochs"],
    ["Horizon-end mean variance · conditional", number(forecast[forecast.length - 1]?.mean_variance)],
  ];
  if (run.method === "p") {
    const decision = plan.decision || {}, budget = plan.budget || {}, risk = plan.target_risk || {}, ending = plan.mission_end_forecast || {};
    const capped = (plan.candidates || []).filter((item) => item.status === "not_evaluated").length;
    // Derive counts from statuses so historical bundles with old counters render correctly too.
    const evaluated = (plan.candidates || []).filter((item) => item.status === "accepted" || item.status === "rejected").length;
    const rejected = (plan.candidates || []).filter((item) => item.status === "rejected").length;
    diagnostics.unshift(["What happened", decisionSentence(plan) || "—"]);
    diagnostics.push(
      ["Retained → selected mission-end variance", `${finite(decision.retained_mission_end_mean_variance) ? number(decision.retained_mission_end_mean_variance) : "no retained plan"} → ${number(decision.selected_mission_end_mean_variance)}`],
      ["Expected gain vs switch margin", `${finite(decision.expected_gain) ? number(decision.expected_gain) : "—"} vs ${number(decision.switch_margin_variance)}`],
      ["Candidates evaluated / rejected / capped", `${evaluated} / ${rejected} / ${capped}`],
      ["Remaining budget · epochs / time", `${budget.remaining_sample_epochs ?? "—"} epochs / ${number(budget.remaining_time_s, 1)} s`],
      ["P's mission-end forecast · upper candidate", `${number(ending.mean_variance)} with ${ending.continuation_epochs ?? "—"} hold epoch(s)`],
      ["Fixed mission target", finite(risk.target_mean_variance) ? number(risk.target_mean_variance) : "not set"],
      ["Target against the forecast", targetSentence(plan)],
    );
  }
  for (const [label, value] of diagnostics) { const item = document.createElement("div"), term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = label; description.textContent = value; if (["What happened", "Target against the forecast"].includes(label)) item.className = "lead"; item.append(term, description); list.append(item); }
  const series = [{ color: methodInfo(run.method).color, points: forecast.map((point) => [point.time_s, point.mean_variance]), dash: [4, 4] }];
  const ending = plan.mission_end_forecast || {}, last = forecast[forecast.length - 1], target = plan.target_risk?.target_mean_variance;
  const hold = run.method === "p" && last && finite(ending.mean_variance) && finite(plan.mission_end_s);
  if (hold) series.push({ color: "#b1bccd", points: [[last.time_s, last.mean_variance], [plan.mission_end_s, ending.mean_variance]], dash: [1, 3] });
  if (run.method === "p" && finite(target) && finite(plan.mission_end_s)) series.push({ color: "#f6a18a", points: [[plan.generated_at_s, target], [plan.mission_end_s, target]], dash: [6, 3] });
  $("#legend-hold").hidden = !hold; $("#legend-target").hidden = !(run.method === "p" && finite(target));
  drawChart($("#plan-forecast-chart"), series, state.playTime, { compact: true });
  if (run.method === "p") {
    $("#plan-scope").textContent = `Dotted map lines and square markers show the commanded cells this plan steers to; the forecast is computed at the positions a nominal controller rollout says the fleet would reach, using no future disturbance, dropout or ground truth. The mission-end value adds an executable hold continuation so every candidate is scored over the same remaining epochs, which makes it an upper candidate from an executable plan, never an attainability floor, a recovery certificate or an RMSE promise. A target this candidate set misses is a statement about a bounded search, not an impossibility result.${run.config?.gp_backend === "sogp" ? " SOGP forecast: frozen approximate posterior, without future dictionary admission or label-dependent pruning, so it carries no bound property." : ""}`;
    return;
  }
  $("#plan-scope").textContent = `Dotted map lines and square markers show this plan's geometric waypoint schedule; labels are planned sample times. The conditional variance forecast ends at the displayed planning horizon, which may precede the mission deadline, and assumes expected observations, not guaranteed QP endpoints.${run.config?.gp_backend === "sogp" ? " SOGP forecast: frozen approximate posterior, without future dictionary admission or label-dependent pruning." : ""} No full belief-MDP optimum, controller rollout, budget-recovery state, or physical safety claim is implied.${plan.planning_scope ? ` Logged scope: ${typeof plan.planning_scope === "string" ? plan.planning_scope : JSON.stringify(plan.planning_scope)}.` : ""}`;
}

function renderControl() {
  const run = currentRun();
  $("#control-panel").hidden = !run;
  if (!run) return;
  const summary = run.summary || {}, control = currentControl(run), qp = controllerMode(run) === "qp", complete = isCompleted(run);
  const arc = run.config?.model === "usv_curvature";
  $("#controller-mode").textContent = qp ? "M1 velocity QP · holonomic constraints" : arc ? "Certified arc filter · turn-constrained USV" : "v0 geometric filter · legacy-compatible";
  $("#run-outcome").textContent = `${complete ? "COMPLETED" : runStatus(run).toUpperCase()} · ${number(completedTime(run), 1)} / ${number(run.config?.duration_s, 1)} s`;
  $("#run-outcome").classList.toggle("failed", !complete);
  $("#run-failure").hidden = complete;
  const failure = run.failure || {};
  $("#run-failure").textContent = complete ? "" : `Partial mission — ${failure.reason || "mission did not complete"}${failure.phase ? ` · ${failure.phase}` : ""}${finite(failure.time_s) ? ` at ${number(failure.time_s, 2)} s` : ""}. Curves and ledger end at the last recorded state; this run is excluded from final-RMSE comparisons.`;
  const diagnostics = qp ? [
    ["Execution solves / failed", `${summary.qp_solves ?? "—"} / ${summary.qp_failures ?? "—"}`],
    ["Preview solves / failed", `${summary.preview_qp_solves ?? "—"} / ${summary.preview_qp_failures ?? "—"}`],
    ["Execution control time · total", `${number(summary.control_s, 3)} s`],
    ["Preview control time · total", `${number(summary.control_preview_s, 3)} s`],
    ["Execution control · median / p95", `${number(summary.control_median_s, 5)} / ${number(summary.control_p95_s, 5)} s`],
    ["Control interventions", String(summary.control_interventions ?? "—")],
    ["Replay solver status", control.status || "No solve at this frame"],
    ["Iterations · this solve", String(control.iterations ?? "—")],
    ["Primal / dual residual", `${scientific(control.primal_residual)} / ${scientific(control.dual_residual)}`],
    ["Max constraint violation", scientific(control.max_constraint_violation)],
    ["Solve / wall · this step", `${number(control.solve_s, 5)} / ${number(control.wall_s, 5)} s`],
  ] : arc ? (() => {
    const executed = (run.controls || []).filter((event) => event.phase === "execution");
    return [
      ["Filter-modified steps · whole mission", `${executed.filter((event) => event.status === "modified").length} / ${executed.length}`],
      ["Robots held on loiter circle · at cursor", Array.isArray(control.loitering) ? `${control.loitering.filter(Boolean).length} of ${control.loitering.length}` : "—"],
      ["Speed scale per robot · at cursor", Array.isArray(control.speed_scales) ? control.speed_scales.map((value) => number(value, 2)).join(" · ") : "—"],
      ["Certified arc separation · at cursor", finite(control.certified_arc_separation) ? `${number(control.certified_arc_separation, 2)} m` : "—"],
      ["Minimum separation · whole mission", `${number(summary.min_separation, 2)} m`],
      ["Control time · total", `${number(summary.control_s, 3)} s`],
    ];
  })() : [
    ["Constraint interventions", String(summary.control_interventions ?? summary.safety_interventions ?? "—")],
    ["Control time · total", finite(summary.control_s) ? `${number(summary.control_s, 3)} s` : "Not logged in legacy run"],
    ["QP solver", "Not used"],
  ];
  if (!complete && failure.details) diagnostics.push(
    ["Rejected solve status", failure.details.status || "—"],
    ["Rejected solve primal / dual", `${scientific(failure.details.primal_residual)} / ${scientific(failure.details.dual_residual)}`],
  );
  const list = $("#control-diagnostics"); list.replaceChildren();
  for (const [label, value] of diagnostics) { const item = document.createElement("div"), term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = label; description.textContent = value; item.append(term, description); list.append(item); }
  $("#control-scope").textContent = qp
    ? "QP receives the current, speed-capped velocity tracking perturbation before propagation. Constraints are checked for this holonomic simulation; no claim covers unknown post-control disturbances or physical robot safety. Diagnostics at the replay cursor are not whole-mission maxima."
    : arc
      ? "Every executed arc keeps each robot inside the field, with a private loiter circle and 2 m separation. The filter never stops a robot: it lowers its speed or holds it on its loiter circle. These are checks inside a kinematic model with no current or hydrodynamics, not a safety certificate for a real boat."
      : "The geometric filter scales the jointly requested step until bounds and pairwise separation pass. It is not a QP solver. USV validation remains kinematic, with bounded turn rate and no hydrodynamics.";
}

function renderSummary() {
  const comparison = state.comparison;
  for (const card of $$(".method-card")) {
    const run = comparison.runs.find((item) => item.method === card.dataset.method), summary = run?.summary || {};
    const complete = isCompleted(run);
    card.querySelector('[data-metric="rmse"]').textContent = complete ? number(summary.rmse) : "—";
    card.querySelector('[data-metric="samples"]').textContent = run && !complete ? `${runStatus(run).toUpperCase()} · ${number(completedTime(run), 1)} s` : `${summary.samples_received ?? "—"} observations`;
    card.classList.toggle("failed", Boolean(run) && !complete);
    card.title = run && !complete ? `Partial-run RMSE ${number(summary.rmse)} is not a final-mission comparison.` : "Final map RMSE after the completed mission";
    card.disabled = !run;
    card.hidden = !run;
  }
  $(".method-cards").classList.toggle("has-dp", comparison.runs.some((run) => PLANNERS.includes(run.method)));
  for (const entry of $$("[data-legend-method]")) entry.hidden = !comparison.runs.some((run) => run.method === entry.dataset.legendMethod);
  const tbody = $("#summary-table"); tbody.replaceChildren();
  for (const run of comparison.runs) {
    const row = document.createElement("tr"), summary = run.summary || {}, nameCell = document.createElement("td"), dot = document.createElement("i");
    dot.className = "table-method-dot"; dot.style.background = methodInfo(run.method).color; nameCell.append(dot, document.createTextNode(methodInfo(run.method).short)); row.append(nameCell);
    const statusCell = document.createElement("td"), label = document.createElement("span"), elapsed = document.createElement("small");
    label.className = `ledger-status${isCompleted(run) ? "" : " failed"}`; label.textContent = runStatus(run).toUpperCase();
    elapsed.textContent = `${number(completedTime(run), 1)} / ${number(run.config?.duration_s, 1)}`; statusCell.append(label, elapsed); row.append(statusCell);
    for (const value of [number(summary.path_length, 1), `${summary.samples_received ?? "—"} / ${summary.samples_attempted ?? "—"}`, number(summary.min_separation, 2), number(summary.runtime_s, 2)]) { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }
    tbody.append(row);
  }
  const greedy = comparison.runs.find((run) => run.method === "greedy" && isCompleted(run))?.summary;
  const adaptive = comparison.runs.find((run) => run.method === "adaptive" && isCompleted(run))?.summary;
  const incomplete = comparison.runs.filter((run) => !isCompleted(run));
  const b3 = comparison.runs.find((run) => run.method === "dp" && isCompleted(run))?.summary;
  const managed = comparison.runs.find((run) => run.method === "p" && isCompleted(run))?.summary;
  let note = "Inspect the curves as well as the final metric. This is one paired scenario, not a statistical performance claim.";
  if (finite(b3?.rmse) && finite(managed?.rmse) && b3.rmse > 1e-12) {
    const change = (b3.rmse - managed.rmse) / b3.rmse * 100;
    note = Math.abs(change) < .05 ? "P and B3 reach the same final RMSE in this run. One seed is not evidence; the held-out comparisons found no significant difference." : `P's final RMSE is ${Math.abs(change).toFixed(1)}% ${change > 0 ? "lower" : "higher"} than B3's in this run. One seed is not evidence; the held-out comparisons found no significant difference.`;
  } else if (finite(greedy?.rmse) && finite(adaptive?.rmse) && greedy.rmse > 1e-12) {
    const change = (greedy.rmse - adaptive.rmse) / greedy.rmse * 100;
    note = Math.abs(change) < .05 ? "Adaptive and nominal greedy final RMSE are nearly equal in this run. A single seed is not a statistical performance claim." : `Adaptive greedy's final RMSE is ${Math.abs(change).toFixed(1)}% ${change > 0 ? "lower" : "higher"} than nominal greedy's in this run. This single-seed result is not a general guarantee.`;
  }
  if (incomplete.length) note = `${incomplete.map((run) => methodInfo(run.method).short).join(", ")}: mission incomplete. Their ledger and curves are partial, not completed-mission scores. No overall method ranking is reported.`;
  $("#comparison-note").textContent = note;
  $("#comparison-note").classList.toggle("failed", Boolean(incomplete.length));
  const config = comparison.runs[0]?.config || {}, robots = config.robot_count ?? config.robots ?? comparison.runs[0]?.initial_positions?.length;
  $("#ledger-subtitle").textContent = `${incomplete.length ? "Partial + completed logs" : "Final metrics"} · ${robots || "—"} robots · ${comparison.scenario || config.scenario || "shared scenario"} · seed ${config.seed ?? config.master_seed ?? "—"} · ${config.controller === "qp" ? "QP" : "geometric filter"} · ${config.gp_backend === "sogp" ? `SOGP (${config.sogp_max_basis} basis limit)` : "exact GP"}`;
  $("#constraint-limits").textContent = `${number(config.max_speed, 1)} m/s · ${number(config.min_separation, 1)} m separation`;
  $("#scope-note").textContent = `Independent ${config.gp_backend === "sogp" ? "sparse-online" : "exact"} GP simulator. Not an ECC paper reproduction. ${config.model === "usv" ? `USV v0: kinematic unicycle, ≤ ${number(config.max_turn_rate, 2)} rad/s; drift yaw-rate std ${number(config.drift_strength, 2)} rad/s. Zero-speed yaw allowed, no hydrodynamics.` : config.model === "usv_curvature" ? `Turn-constrained USV: forward only, minimum turning radius ${number(config.max_speed / config.max_turn_rate, 2)} m, no turning on the spot; ${config.drift_strength > 0 ? `drift is a ${number(config.drift_strength, 2)} rad/s yaw-rate tracking error` : "no drift in this scenario"}. Kinematic model, no current or hydrodynamics.` : `Holonomic kinematics; drift velocity std ${number(config.drift_strength, 2)} m/s. Discrete motion constraints.`}`;
  $("#mission-runtime").textContent = `${number(comparison.runtime_s, 1)} s COMPUTE · ${comparison.runs.length} METHODS`;
  $("#result-badge").textContent = incomplete.length ? `${incomplete.length} INCOMPLETE` : "REPLAY AVAILABLE"; $("#result-badge").classList.toggle("complete", !incomplete.length); $("#result-badge").classList.toggle("failed", Boolean(incomplete.length));
  $("#export-json").disabled = false;
  const counts = comparison.runs.map((run) => run.summary?.control_interventions ?? run.summary?.safety_interventions);
  const interventions = counts.every(finite) ? `${counts.reduce((sum, value) => sum + value, 0)} constraint interventions across these recorded runs.` : "Constraint intervention totals are unavailable for some recorded runs.";
  $("#safety-note").textContent = `${interventions} Runtime includes GP updates, planning, control and simulation. Constraints are checked under this simulation model; no real-world safety guarantee is implied.`;
}

function useComparison(payload) {
  const comparison = payload?.comparison || payload;
  if (!Array.isArray(comparison?.runs) || !comparison.runs.length) return false;
  if (!comparison.runs.every((run) => Array.isArray(run.frames) && run.frames.length && run.field && run.summary)) throw new Error("The saved comparison is missing required simulation fields.");
  setPlaying(false); state.comparison = comparison; state.heat = {}; state.showcase = null; computeScales();
  const config = comparison.config || comparison.runs[0].config || {};
  if (SCENARIOS[comparison.scenario]) $("#scenario").value = comparison.scenario;
  if (finite(config.robot_count ?? config.robots)) $("#robots").value = config.robot_count ?? config.robots;
  if (finite(config.seed)) $("#seed").value = config.seed;
  if (finite(config.duration_s)) $("#duration").value = config.duration_s;
  if (["holonomic", "usv", "usv_curvature"].includes(config.model)) $("#model").value = config.model;
  $("#target").value = finite(config.target_mean_variance) ? config.target_mean_variance : "";
  $("#controller").value = config.controller === "qp" ? "qp" : "filter";
  $("#gp-backend").value = config.gp_backend === "sogp" ? "sogp" : "exact";
  const capacity = String(config.sogp_max_basis ?? 64), capacitySelector = $("#sogp-max-basis");
  if (![...capacitySelector.options].some((option) => option.value === capacity)) { const option = document.createElement("option"); option.value = capacity; option.textContent = `${capacity} basis points · loaded config`; capacitySelector.append(option); }
  capacitySelector.value = capacity;
  $("#sogp-novelty-tolerance").value = config.sogp_novelty_tolerance ?? 1e-6;
  $("#include-dp").checked = comparison.runs.some((run) => run.method === "dp");
  $("#include-p").checked = comparison.runs.some((run) => run.method === "p");
  updateScenarioHelp(); updateControllerHelp(); updateGPHelp();
  if (!comparison.runs.some((run) => run.method === state.method)) state.method = comparison.runs[0].method;
  setReplayTime(lastFrame(currentRun()).time_s);
  renderSummary(); selectMethod(state.method); renderStory();
  // The server may include a verified video URL, otherwise status controls it.
  if (typeof payload?.video_url === "string" && payload.video_url.startsWith("/")) { $("#video-link").href = payload.video_url; state.videoAvailable = true; }
  updateVideo();
  return true;
}

function updateVideo() {
  $("#video-link").classList.toggle("disabled", !state.videoAvailable);
  $("#video-link").setAttribute("aria-disabled", String(!state.videoAvailable));
}

async function fetchStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    state.videoAvailable = Boolean(payload.video_available || payload.video_url);
    if (typeof payload.video_url === "string" && payload.video_url.startsWith("/")) $("#video-link").href = payload.video_url;
    updateVideo();
    const capabilities = payload.capabilities || payload;
    if (Array.isArray(capabilities.models)) for (const option of $("#model").options) option.disabled = !capabilities.models.includes(option.value);
    if (finite(capabilities.max_duration_s)) $("#duration").max = capabilities.max_duration_s;
    if (finite(capabilities.min_duration_s)) $("#duration").min = capabilities.min_duration_s;
  } catch { /* The status endpoint is optional. Run errors remain visible. */ }
}

async function runComparison(event) {
  event.preventDefault(); if (state.busy) return;
  updateControllerHelp();
  const payload = { scenario: $("#scenario").value, robots: Number($("#robots").value), model: $("#model").value, controller: $("#controller").value, gp_backend: $("#gp-backend").value, seed: Number($("#seed").value), duration_s: Number($("#duration").value) };
  if (payload.gp_backend === "sogp") { payload.sogp_max_basis = Number($("#sogp-max-basis").value); payload.sogp_novelty_tolerance = Number($("#sogp-novelty-tolerance").value); }
  const extras = [...($("#include-dp").checked ? ["dp"] : []), ...($("#include-p").checked ? ["p"] : [])];
  if (extras.length) payload.methods = ["sweep", "greedy", "adaptive", ...extras];
  const target = Number($("#target").value);
  if ($("#include-p").checked && $("#target").value !== "" && Number.isFinite(target) && target > 0) payload.target_mean_variance = target;
  state.busy = true; setPlaying(false); $("#mission-fields").disabled = true; $("#error-box").hidden = true; $("#run-label").textContent = "Simulation running…";
  const start = performance.now();
  const updateStatus = () => status(`Running ${payload.methods?.length || 3} methods · ${((performance.now() - start) / 1000).toFixed(0)} s elapsed. Waiting for actual results.`, "busy");
  updateStatus(); const timer = setInterval(updateStatus, 1000);
  try {
    const response = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error(`The local simulator returned ${response.status} instead of JSON. Check its terminal output.`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.message || `Simulation failed (${response.status}).`);
    if (!useComparison(result)) throw new Error("The simulator returned no recorded runs.");
    const failed = state.comparison.runs.filter((run) => !isCompleted(run)).length;
    clearInterval(timer); status(failed ? `Comparison recorded · ${failed} incomplete mission${failed > 1 ? "s" : ""}. Inspect the failure ledger.` : `Comparison complete · ${number(state.comparison.runtime_s, 1)} s compute.`, failed ? "idle" : "ready");
    fetchStatus();
  } catch (error) {
    clearInterval(timer); $("#error-box").textContent = error.message || "Unable to reach the local simulator."; $("#error-box").hidden = false;
    status(state.comparison ? "Run failed. Previous results remain available." : "Run failed. Check the local simulator terminal.", "idle");
  } finally { clearInterval(timer); state.busy = false; $("#mission-fields").disabled = false; $("#run-label").textContent = "Run comparison"; }
}

$("#run-form").addEventListener("submit", runComparison);
$("#scenario").addEventListener("change", updateScenarioHelp);
$("#model").addEventListener("change", () => { updateScenarioHelp(); updateControllerHelp(); });
$("#controller").addEventListener("change", updateControllerHelp);
$("#gp-backend").addEventListener("change", updateGPHelp);
$$(".method-card").forEach((card) => card.addEventListener("click", () => selectMethod(card.dataset.method)));
$$("[data-layer]").forEach((button) => button.addEventListener("click", () => {
  state.layer = button.dataset.layer;
  $$("[data-layer]").forEach((item) => { const selected = item === button; item.classList.toggle("active", selected); item.setAttribute("aria-pressed", String(selected)); });
  renderReplay();
}));
$("#show-planned").addEventListener("change", drawMaps);
$("#include-p").addEventListener("change", updateControllerHelp);
$("#compare-toggle").addEventListener("click", () => { state.compare = !state.compare; renderReplay(); });
$("#story-jump").addEventListener("click", jumpToKeyMoment);
$("#replay-slider").addEventListener("input", (event) => { setPlaying(false); setReplayTime(motionRecords()[Number(event.target.value)]?.time_s || 0); renderReplay(); });
$("#play-button").addEventListener("click", () => {
  if (state.playing) { setPlaying(false); return; }
  if (state.motionIndex >= motionRecords().length - 1) { setReplayTime(0); renderReplay(); }
  setPlaying(true);
});
$("#export-json").addEventListener("click", () => {
  if (!state.comparison) return;
  const blob = new Blob([JSON.stringify(state.comparison, null, 2)], { type: "application/json" }), url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = `fieldwork-comparison-seed-${state.comparison.runs[0]?.config?.seed ?? "run"}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
const resizeObserver = new ResizeObserver(() => { drawMaps(); renderCharts(); renderPlan(); });
for (const canvas of $$("canvas")) resizeObserver.observe(canvas);

// Guided showcases: recorded comparisons on development seeds, pinned by the server.
async function loadShowcases() {
  try {
    const response = await fetch("/api/showcases", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    state.showcases = Array.isArray(payload.showcases) ? payload.showcases : [];
  } catch { return; }
  const box = $("#showcase-cards"); box.replaceChildren();
  state.showcases.forEach((entry, index) => {
    const card = document.createElement("button"), config = entry.config || {};
    card.type = "button"; card.className = "showcase-card"; card.dataset.showcase = entry.id;
    const label = Object.assign(document.createElement("span"), { className: "showcase-number", textContent: `SHOWCASE ${index + 1}` });
    const title = Object.assign(document.createElement("strong"), { textContent: entry.title });
    const question = Object.assign(document.createElement("span"), { className: "showcase-question", textContent: entry.question });
    const meta = Object.assign(document.createElement("span"), { className: "showcase-meta", textContent: `${(MODEL_LABELS[config.model] || config.model || "").toUpperCase()} · ${String(config.scenario || "").toUpperCase()} · SEED ${config.seed ?? "—"}` });
    card.append(label, title, question, meta);
    card.addEventListener("click", () => openShowcase(entry.id));
    box.append(card);
  });
  $("#showcases").hidden = !state.showcases.length;
}

async function openShowcase(id) {
  const entry = state.showcases.find((item) => item.id === id);
  if (!entry || state.busy) return;
  status(`Loading showcase · ${entry.title}…`, "busy"); $("#error-box").hidden = true;
  try {
    const response = await fetch(`/api/showcase/${encodeURIComponent(id)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Showcase unavailable (${response.status}).`);
    if (!useComparison(payload)) throw new Error("The showcase recording has no runs.");
    state.showcase = entry;
    state.compare = Boolean(entry.compare) && canCompare();
    if (runOf(entry.focus)) selectMethod(entry.focus);
    jumpToKeyMoment(); renderStory();
    status(`Showcase loaded · ${entry.title}. Press play or scrub the replay.`, "ready");
  } catch (error) {
    $("#error-box").textContent = error.message || "Unable to load the showcase."; $("#error-box").hidden = false;
    status("Showcase could not be loaded. Run scripts/make_showcases.py first.", "idle");
  }
}

function jumpToKeyMoment() {
  if (!state.showcase) return;
  setPlaying(false); setReplayTime(state.showcase.key_time_s); renderReplay();
}

function renderStory() {
  const entry = state.showcase;
  $("#story-panel").hidden = !entry;
  $$(".showcase-card").forEach((card) => card.classList.toggle("active", card.dataset.showcase === entry?.id));
  if (!entry) return;
  const index = state.showcases.findIndex((item) => item.id === entry.id);
  $("#story-kicker").textContent = `SHOWCASE ${index + 1} · DEVELOPMENT SEED ${entry.config?.seed ?? "—"} · AN ILLUSTRATION, NOT EVIDENCE`;
  $("#story-title").textContent = entry.title;
  $("#story-question").textContent = entry.question;
  $("#story-moment").textContent = entry.key_moment;
  $("#story-jump").textContent = `Jump to the key moment · ${number(entry.key_time_s, 1)} s`;
  $("#story-look").replaceChildren(...(entry.look_for || []).map((text) => Object.assign(document.createElement("li"), { textContent: text })));
  $("#story-facts").replaceChildren(...(entry.facts || []).map(([label, value]) => {
    const item = document.createElement("div");
    item.append(Object.assign(document.createElement("dt"), { textContent: label }), Object.assign(document.createElement("dd"), { textContent: value }));
    return item;
  }));
  $("#story-evidence").textContent = entry.evidence;
}

async function initialize() {
  updateScenarioHelp(); updateControllerHelp(); updateGPHelp();
  renderReplay();
  const statusPromise = fetchStatus();
  loadShowcases();
  try {
    const response = await fetch("/api/latest", { cache: "no-store" });
    if (response.status === 404 || response.status === 204) status("Ready. Configure a mission and run a comparison.", "idle");
    else if (response.ok) { const loaded = useComparison(await response.json()); status(loaded ? "Saved comparison loaded. Replay or run a new mission." : "Ready. Configure a mission and run a comparison.", loaded ? "ready" : "idle"); }
    else status("Ready to run. No saved comparison could be loaded.", "idle");
  } catch { status("Start the local demo server to connect the simulator.", "idle"); }
  await statusPromise;
}
initialize();
