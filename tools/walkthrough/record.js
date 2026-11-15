/*
 * Records a narration-free walkthrough video of the app.
 *
 * It starts the Django server (serving the built frontend), drives the UI in a
 * headless Chromium with Playwright, overlays large captions and a visible
 * cursor, records the session at 1080p and converts it to MP4.
 *
 *   cd frontend && npm run build && cd ../backend && python manage.py collectstatic --noinput
 *   cd tools/walkthrough && npm install && npx playwright install chromium && npm run record
 *
 * Env: APP_URL (skip starting the server), ORIGIN / DESTINATION / LOAD, OUTPUT (mp4 path).
 */
/* eslint-disable no-console */
const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const BACKEND = path.join(ROOT, 'backend');
const PY =
  process.platform === 'win32'
    ? path.join(BACKEND, '.venv', 'Scripts', 'python.exe')
    : path.join(BACKEND, '.venv', 'bin', 'python');
const PORT = Number(process.env.PORT || 8766);
const BASE = process.env.APP_URL || `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.join(__dirname, 'out');
const FINAL = process.env.OUTPUT || path.join(ROOT, 'walkthrough.mp4');

const TRIP = {
  originQuery: process.env.ORIGIN || 'Portland',
  originMatch: process.env.ORIGIN_MATCH || 'Oregon',
  destinationQuery: process.env.DESTINATION || 'Boise',
  destinationMatch: process.env.DESTINATION_MATCH || 'Idaho',
  load: Number(process.env.LOAD || 45000),
};

const VIEWPORT = { width: 1920, height: 1080 };
const SIDEBAR_WIDTH = 440;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);

// ---------------------------------------------------------------- overlay

function installOverlay() {
  const style = document.createElement('style');
  style.textContent = `
    #demo-caption{position:fixed;top:22px;left:calc(440px + (100vw - 440px)/2);transform:translateX(-50%);z-index:100000;
      max-width:1180px;background:rgba(15,23,42,.93);color:#fff;padding:16px 26px;border-radius:14px;
      font:500 25px/1.4 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.35);
      opacity:0;transition:opacity .35s;pointer-events:none}
    #demo-caption.show{opacity:1}
    #demo-caption .step{display:block;font-size:15px;letter-spacing:.12em;text-transform:uppercase;color:#5eead4;font-weight:700;margin-bottom:4px}
    #demo-card{position:fixed;inset:0;z-index:100001;background:linear-gradient(135deg,#0f3d4a,#0b1f2a);color:#fff;display:flex;
      flex-direction:column;align-items:center;justify-content:center;text-align:center;
      font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;opacity:0;transition:opacity .5s;pointer-events:none;padding:0 120px}
    #demo-card.show{opacity:1}
    #demo-card h1{font-size:66px;margin:0 0 14px;letter-spacing:-.02em}
    #demo-card h2{font-size:28px;font-weight:500;margin:0 0 40px;color:#9fd3e0}
    #demo-card ul{list-style:none;padding:0;margin:0;font-size:27px;line-height:1.75}
    #demo-card li::before{content:"▸";color:#5eead4;margin-right:14px}
    #demo-cursor{position:fixed;z-index:100002;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;
      background:rgba(239,68,68,.55);border:3px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.4);pointer-events:none;
      left:-100px;top:-100px;transition:transform .12s}
    #demo-cursor.click{transform:scale(.65);background:rgba(239,68,68,.95)}
    .demo-highlight{outline:4px solid #f59e0b !important;outline-offset:3px;border-radius:12px}
  `;
  document.head.appendChild(style);
  for (const id of ['demo-caption', 'demo-card', 'demo-cursor']) {
    const el = document.createElement('div');
    el.id = id;
    document.body.appendChild(el);
  }
}

// ---------------------------------------------------------------- helpers

const cursor = { x: VIEWPORT.width / 2, y: VIEWPORT.height / 2 };

async function setCursor(page, x, y) {
  await page.evaluate(
    ([cx, cy]) => {
      const el = document.getElementById('demo-cursor');
      el.style.left = `${cx}px`;
      el.style.top = `${cy}px`;
    },
    [x, y],
  );
}

async function moveTo(page, x, y, ms = 650) {
  const steps = Math.max(10, Math.round(ms / 16));
  const from = { ...cursor };
  for (let i = 1; i <= steps; i++) {
    const t = easeInOut(i / steps);
    const xi = from.x + (x - from.x) * t;
    const yi = from.y + (y - from.y) * t;
    await page.mouse.move(xi, yi);
    await setCursor(page, xi, yi);
    await sleep(16);
  }
  cursor.x = x;
  cursor.y = y;
}

async function click(page, x, y) {
  await moveTo(page, x, y);
  await page.evaluate(() => document.getElementById('demo-cursor').classList.add('click'));
  await page.mouse.down();
  await sleep(90);
  await page.mouse.up();
  await sleep(140);
  await page.evaluate(() => document.getElementById('demo-cursor').classList.remove('click'));
}

async function clickLocator(page, locator) {
  await locator.first().scrollIntoViewIfNeeded();
  await sleep(250);
  const box = await locator.first().boundingBox();
  if (!box) throw new Error(`Element not visible: ${locator}`);
  await click(page, box.x + box.width / 2, box.y + box.height / 2);
}

async function caption(page, step, text, hold = 0) {
  await page.evaluate(
    ([s, t]) => {
      const el = document.getElementById('demo-caption');
      el.innerHTML = (s ? `<span class="step">${s}</span>` : '') + t;
      el.classList.add('show');
    },
    [step, text],
  );
  if (hold) await sleep(hold);
}

async function hideCaption(page) {
  await page.evaluate(() => document.getElementById('demo-caption').classList.remove('show'));
}

async function card(page, html, hold) {
  await page.evaluate((h) => {
    const el = document.getElementById('demo-card');
    el.innerHTML = h;
    el.classList.add('show');
  }, html);
  await sleep(hold);
  await page.evaluate(() => document.getElementById('demo-card').classList.remove('show'));
  await sleep(600);
}

async function highlight(page, selector, hold) {
  await page.evaluate((s) => document.querySelector(s)?.classList.add('demo-highlight'), selector);
  await sleep(hold);
  await page.evaluate((s) => document.querySelector(s)?.classList.remove('demo-highlight'), selector);
}

async function typeInto(page, locator, text) {
  await clickLocator(page, locator);
  await locator.fill('');
  await page.keyboard.type(text, { delay: 90 });
}

async function pickSuggestion(page, match) {
  await page.waitForSelector('.suggestions li', { timeout: 20000 });
  await sleep(1100);
  const items = page.locator('.suggestions li');
  const count = await items.count();
  let target = items.first();
  for (let i = 0; i < count; i++) {
    if ((await items.nth(i).innerText()).includes(match)) {
      target = items.nth(i);
      break;
    }
  }
  await clickLocator(page, target);
}

async function latLngToScreen(page, lat, lng) {
  return page.evaluate(
    ([la, ln]) => {
      const map = window.__leafletMap;
      const p = map.latLngToContainerPoint([la, ln]);
      const r = map.getContainer().getBoundingClientRect();
      return [r.left + p.x, r.top + p.y];
    },
    [lat, lng],
  );
}

async function dragSlider(page, slider, fromFraction, toFraction, ms) {
  const box = await slider.boundingBox();
  const y = box.y + box.height / 2;
  const x0 = box.x + 8 + (box.width - 16) * fromFraction;
  const x1 = box.x + 8 + (box.width - 16) * toFraction;
  await moveTo(page, x0, y);
  await page.mouse.down();
  const steps = Math.max(20, Math.round(ms / 40));
  for (let i = 1; i <= steps; i++) {
    const x = x0 + (x1 - x0) * (i / steps);
    await page.mouse.move(x, y);
    await setCursor(page, x, y);
    await sleep(ms / steps);
  }
  await page.mouse.up();
  cursor.x = x1;
  cursor.y = y;
}

function waitForHealth(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(`${url}/api/health/`, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else retry();
        })
        .on('error', retry);
    };
    const retry = () => {
      if (Date.now() > deadline) reject(new Error('server did not start'));
      else setTimeout(attempt, 500);
    };
    attempt();
  });
}

// ---------------------------------------------------------------- scenario

async function run(page) {
  page.setDefaultTimeout(90000);
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.evaluate(installOverlay);
  await setCursor(page, cursor.x, cursor.y);
  await sleep(600);

  await card(
    page,
    `<h1>Weather-Aware Truck Routing</h1>
     <h2>React + TypeScript + Leaflet &nbsp;·&nbsp; Django + Django REST framework</h2>
     <ul>
       <li>Three route options from the OSRM routing API</li>
       <li>Forecast sampled every 10 / 25 / 50 miles at the truck's ETA (Open-Meteo)</li>
       <li>Wind · rain · snow risk rules with load-weight escalation</li>
       <li>Ranked recommendation, risk-coloured map, 0–48 h corridor heatmap</li>
     </ul>`,
    9000,
  );

  // ---- Step 1: inputs
  await caption(
    page,
    'Step 1 · Enter the trip',
    'Origin and destination use live geocoding autocomplete (Photon / OpenStreetMap). Free text or “lat, lon” also works.',
  );
  const inputs = page.locator('.place-field input');
  await typeInto(page, inputs.nth(0), TRIP.originQuery);
  await pickSuggestion(page, TRIP.originMatch);
  await sleep(700);
  await typeInto(page, inputs.nth(1), TRIP.destinationQuery);
  await pickSuggestion(page, TRIP.destinationMatch);
  await sleep(900);

  await caption(
    page,
    'Step 1 · Enter the trip',
    `Departure defaults to the next hour. Load weight matters: wind risk is escalated above 30,000 lb and 40,000 lb. Here: ${TRIP.load.toLocaleString()} lb, checkpoints every 25 miles.`,
  );
  await clickLocator(page, page.locator('button.chip', { hasText: TRIP.load.toLocaleString() }));
  await sleep(900);
  await clickLocator(page, page.locator('.plan-form .segmented button', { hasText: '25 mi' }));
  await sleep(1800);

  await caption(
    page,
    'Step 1 · Plan',
    'One request: geocode → OSRM routes (alternatives + synthesized detours) → checkpoints with ETAs → one batched forecast call → risk rules → ranking.',
  );
  const planResponse = page.waitForResponse(
    (r) => r.url().includes('/api/plan/') && r.request().method() === 'POST',
    { timeout: 180000 },
  );
  await clickLocator(page, page.locator('button.primary'));
  const plan = await (await planResponse).json();
  await page.waitForSelector('.recommendation', { timeout: 180000 });
  await sleep(2200); // fitBounds animation
  const recommended = plan.routes.find((r) => r.recommended);
  const other = plan.routes.find((r) => !r.recommended) || recommended;

  // ---- Step 2: map
  await caption(
    page,
    'Step 2 · Routes on the map',
    `${plan.routes.length} route options. The selected route is coloured per checkpoint by risk level; alternatives are grey. Labels sit where the routes diverge and show drive time, distance and rank.`,
    11000,
  );

  await caption(
    page,
    'Step 2 · Checkpoints',
    "Every checkpoint carries the truck's ETA, the forecast at that ETA (wind, gusts, rain, snow, temperature) and the risk level with the rule that produced it.",
  );
  const candidates = [];
  if (recommended.summary.max_level !== 'Low' && recommended.summary.worst_checkpoint_index != null) {
    candidates.push(recommended.summary.worst_checkpoint_index);
  }
  const n = recommended.checkpoints.length;
  candidates.push(Math.floor(n / 2), Math.floor(n / 3), Math.floor((2 * n) / 3), Math.floor(n / 4));
  let opened = false;
  for (const idx of candidates) {
    const cp = recommended.checkpoints[idx];
    const [x, y] = await latLngToScreen(page, cp.lat, cp.lng);
    const insideMap = x > SIDEBAR_WIDTH + 60 && x < VIEWPORT.width - 80 && y > 140 && y < VIEWPORT.height - 260;
    if (!insideMap) continue;
    await click(page, x, y);
    await sleep(700);
    if ((await page.locator('.leaflet-popup').count()) > 0) {
      opened = true;
      break;
    }
  }
  await sleep(opened ? 9000 : 3000);
  if (opened) {
    await page.keyboard.press('Escape');
    await sleep(600);
  }

  // Hover a few more checkpoints to show the quick tooltips.
  await caption(page, 'Step 2 · Checkpoints', 'Hovering shows mile, ETA and risk; the coloured dots and segments follow the risk level of each stretch.');
  let hovered = 0;
  for (const idx of [Math.floor(n / 5), Math.floor((2 * n) / 5), Math.floor((3 * n) / 5), Math.floor((4 * n) / 5)]) {
    const cp = recommended.checkpoints[idx];
    const [x, y] = await latLngToScreen(page, cp.lat, cp.lng);
    if (x > SIDEBAR_WIDTH + 60 && x < VIEWPORT.width - 80 && y > 140 && y < VIEWPORT.height - 260) {
      await moveTo(page, x, y, 900);
      await sleep(1800);
      hovered++;
    }
  }
  if (!hovered) await sleep(3000);

  await caption(
    page,
    'Step 2 · Compare routes',
    `Click a card, a grey line or a label to inspect another option — here ${other.name}. The map, cards and checkpoint table stay in sync.`,
  );
  await clickLocator(page, page.locator('.route-card', { hasText: other.name }));
  await sleep(5500);
  await clickLocator(page, page.locator('.route-label-id', { hasText: new RegExp(`^${recommended.id}$`) }));
  await sleep(3000);

  // ---- Step 3: recommendation
  await caption(
    page,
    'Step 3 · Recommendation',
    'Ranking order: fewest No-Travel miles → fewest Severe miles → fewest High miles → lowest distance-weighted average risk → shortest drive time.',
  );
  await page.locator('.recommendation').scrollIntoViewIfNeeded();
  await highlight(page, '.recommendation', 11000);
  await caption(
    page,
    'Step 3 · Recommendation',
    'The reasons name the first criterion that separates the routes and state the time trade-off against the fastest option.',
  );
  await clickLocator(page, page.locator('.criteria summary'));
  await sleep(7500);

  await caption(
    page,
    'Step 3 · Route cards',
    'Stacked bar = miles per risk level. No-Travel, Severe and High miles plus the weighted average risk are listed for every option.',
  );
  await page.locator('.route-cards').scrollIntoViewIfNeeded();
  await highlight(page, '.route-cards', 7500);

  await caption(
    page,
    'Step 3 · Checkpoint table',
    'Mile, ETA, conditions, wind, rain, snow and risk for the selected route. Clicking a row flies the map to that checkpoint.',
  );
  const rows = page.locator('table.checkpoints tbody tr');
  const rowCount = await rows.count();
  await clickLocator(page, rows.nth(Math.min(rowCount - 1, Math.max(1, Math.floor(rowCount / 2)))));
  await sleep(6000);

  // ---- Step 4: heatmap
  await page.waitForSelector('.forecast-panel input[type=range]:not([disabled])', { timeout: 120000 });
  await caption(
    page,
    'Step 4 · Corridor heatmap',
    'A 48-hour forecast for a grid within 40 miles of every route, blended into a smooth field. Hour 0 is the departure hour — drag the slider to look ahead.',
  );
  const slider = page.locator('.forecast-panel input[type=range]');
  await dragSlider(page, slider, 0, 1, 7000);
  await sleep(1200);
  await dragSlider(page, slider, 1, 0, 2500);
  await sleep(800);

  await caption(
    page,
    'Step 4 · Playback',
    "Press play: the field animates hour by hour and the 🚚 markers show where each route's truck is at that time (arrival ticks sit under the slider).",
  );
  await clickLocator(page, page.locator('.play-btn'));
  await sleep(11000);
  await clickLocator(page, page.locator('.play-btn'));
  await sleep(600);

  const metricNotes = {
    Wind: 'Wind speed in mph — the input to the wind thresholds and the load rules.',
    Rain: 'Rain in inches per hour (rain + showers).',
    Snow: 'Snowfall in inches per hour.',
    Temp: 'Temperature in °F for context (not scored).',
  };
  for (const [metric, note] of Object.entries(metricNotes)) {
    await caption(page, 'Step 4 · Metrics', `${metric}: ${note}`);
    await clickLocator(page, page.locator('.forecast-panel .segmented button', { hasText: metric }));
    await sleep(3800);
  }
  await caption(page, 'Step 4 · Metrics', 'Risk: the combined level per cell, with the load rules applied to the entered load weight.');
  await clickLocator(page, page.locator('.forecast-panel .segmented button', { hasText: 'Risk' }));
  await sleep(3000);

  await caption(
    page,
    'Step 4 · Performance',
    'Inverse-distance weights are precomputed once per view and the field is upscaled with bilinear filtering, so scrubbing, playback and zooming stay smooth.',
  );
  const mapCenter = { x: SIDEBAR_WIDTH + (VIEWPORT.width - SIDEBAR_WIDTH) / 2, y: 470 };
  await moveTo(page, mapCenter.x, mapCenter.y);
  for (let i = 0; i < 3; i++) {
    await page.mouse.wheel(0, -240);
    await sleep(900);
  }
  await sleep(2500);
  await dragSlider(page, slider, 0, 0.5, 3000);
  await sleep(1500);
  await moveTo(page, mapCenter.x, mapCenter.y);
  for (let i = 0; i < 3; i++) {
    await page.mouse.wheel(0, 240);
    await sleep(900);
  }
  await sleep(2500);
  await hideCaption(page);
  await sleep(800);

  await card(
    page,
    `<h1>Under the hood</h1>
     <ul>
       <li>backend/routing/services — risk.py · checkpoints.py · routing.py · summary.py · planner.py</li>
       <li>frontend/src/components/map/HeatCanvasLayer.ts — canvas inverse-distance heatmap</li>
       <li>87 pytest + 8 vitest tests · GitHub Actions CI</li>
       <li>Single Docker image (WhiteNoise + gunicorn) · Render blueprint</li>
     </ul>`,
    9000,
  );
}

// ---------------------------------------------------------------- main

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  let server = null;
  if (!process.env.APP_URL) {
    server = spawn(PY, ['manage.py', 'runserver', `127.0.0.1:${PORT}`, '--noreload'], {
      cwd: BACKEND,
      env: { ...process.env, DJANGO_DEBUG: '0', DJANGO_ALLOWED_HOSTS: '127.0.0.1,localhost', PYTHONUTF8: '1' },
      stdio: 'ignore',
    });
  }
  let exitCode = 0;
  try {
    await waitForHealth(BASE, 60000);
    const browser = await chromium.launch();
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
      locale: 'en-US',
      timezoneId: process.env.TZ_ID || 'America/Denver',
      recordVideo: { dir: OUT_DIR, size: VIEWPORT },
    });
    const page = await context.newPage();
    try {
      await run(page);
    } catch (err) {
      console.error('Scenario failed:', err);
      exitCode = 1;
    }
    await context.close();
    const webm = await page.video().path();
    await browser.close();

    const ffmpeg = require('ffmpeg-static');
    if (ffmpeg && fs.existsSync(ffmpeg)) {
      const result = spawnSync(
        ffmpeg,
        ['-y', '-i', webm, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', FINAL],
        { stdio: 'inherit' },
      );
      if (result.status === 0) {
        console.log(`\nVideo written to ${FINAL}`);
      } else {
        fs.copyFileSync(webm, FINAL.replace(/\.mp4$/, '.webm'));
        console.log(`ffmpeg failed; raw recording copied to ${FINAL.replace(/\.mp4$/, '.webm')}`);
      }
    } else {
      fs.copyFileSync(webm, FINAL.replace(/\.mp4$/, '.webm'));
      console.log(`ffmpeg not available; raw recording copied to ${FINAL.replace(/\.mp4$/, '.webm')}`);
    }
  } finally {
    if (server) server.kill();
  }
  process.exit(exitCode);
})();
