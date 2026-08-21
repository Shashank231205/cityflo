# Is route X running late right now?

## Read this first

This is deliberately under-specified. We did not hand you a spec to execute — we handed you a question and a pile of messy data, the way a real on-call gets it. The judgment is the test: what you choose to model, what you choose to ignore, what you decide is signal versus noise, and what you write down as an assumption instead of silently guessing.

The strongest submissions notice the gaps, make a defensible call, write the assumption down next to the call, and end with the two or three questions they'd have asked an ops lead before shipping this for real. The weakest ones build a tidy pipeline that confidently reports garbage. We would much rather see a small, sharp, correct slice with honest caveats than a sprawling system that trusts its inputs.

This is not a SQL exam. The data is small enough to load into anything; the hard part is deciding what's true. We are not grading visual polish, test coverage, framework choice, or how many anomalies you can list. We are grading whether your answer is *trustworthy* — and whether you can defend it a week later in a room.

## The situation

Cityflo runs premium daily-commute buses for corporate professionals across Mumbai, Hyderabad, Delhi and Kolkata — ~1,200 buses, ~60,000 rides a day, climbing toward five times that. Every bus emits GPS pings. Riders book a seat on a specific trip and board it at a specific stop. Ops watches a wall of routes every morning and needs one number per route, live: **is this route running late right now, and by how much?** That number decides whether they fire a "your bus is 8 min late" push, hold a downstream connection, or call a driver. A wrong number is worse than no number — it burns rider trust and sends ops chasing ghosts.

You have three mornings of real-shaped data from a handful of Mumbai routes. It is raw. Devices lie. Buses idle at the depot with the engine running. GPS smears across a flyover. Some of what looks late is not late, and some of what looks fine is a bus that quietly fell off the map. Your job is to turn this into a defensible "lateness right now" answer for a given route — and to be honest about where it breaks.

## Your task

Design a data model and build a runnable slice that, given the data, a chosen route, and a chosen "as of" timestamp, answers: **is it running late, and by how many minutes?** Concretely:

1. **Model the data.** Decide the shape that lets you answer the question well. You'll probably want a staging layer for raw pings, something that resolves a ping stream into "this vehicle is on this trip and is *here* along the route," and something that turns position-vs-time into a lateness number. Name your grain explicitly — per ping? per vehicle-trip? per route-time-window? Postgres is the house default and the data is sized for it, but use whatever you can defend (DuckDB, SQLite, plain pandas — all fine).

2. **Build the slice.** A script, a handful of SQL views, a notebook — your call. It must ingest the provided files and emit, for a route and an "as of" time, a lateness verdict: a number, plus enough context to trust it. "Runnable" means we can clone it and get an answer for a route we pick. A perfect architecture diagram with nothing that runs is worth less than fifty defensible lines that do.

3. **Define "late" yourself.** We deliberately did not hand you a definition of schedule adherence. Late against the timetable? Against the typical time-of-day runtime for that route? Against the arrival time the rider was promised in-app? Against distance-remaining at current speed? Each is defensible and each breaks differently. Pick one, justify it, and state what you'd need to do it properly. We care more about *why* you picked one than which one you picked.

4. **Surface what the data reveals.** Look at it before you trust it. There are real artifacts in here — device and behaviour quirks that will wreck a naive lateness calc and that an LLM, left to its own devices, will average straight past. Find what you can, decide what to do with each (exclude? flag? correct? withhold the verdict and say why?), and write down your reasoning. We care far more about your *treatment* of one bad case than a tidy catalogue of all of them. A pipeline that reports a parked bus as 40 minutes late has failed this assignment even if the SQL is beautiful.

Then write the memo. We want the reasoning at least as much as the code.

## What we provide

The bundle is fetchable at **https://careers.cityflo.com/takehomes/data-engineer/** and is attached to this assignment:

- `BRIEF.md` — this brief.
- `DATA_GUIDE.md` — column-level notes on every file, route metadata, and a short handoff note from the analyst who pulled the extract. Read it — but treat it the way you'd treat any handoff: a starting point, not gospel. **The data is the source of truth; the notes only describe what someone *believed* about it when they pulled it.**
- `data/gps_pings.csv` — raw pings: `ping_id, vehicle_id, operator_id, lat, lon, speed_kmph, recorded_at` (device clock, IST), `received_at` (server ingest clock, IST). ~3 mornings, a handful of buses.
- `data/trips.csv` — scheduled trips: `trip_id, route_id, vehicle_id, service_date, scheduled_start, scheduled_end, direction`.
- `data/bookings.csv` — rider bookings: `booking_id, trip_id, rider_id, boarding_stop_id, booked_at, promised_eta`.
- `data/routes.csv` — `route_id, route_name, origin_stop, dest_stop, scheduled_runtime_min, stops_count`.
- `data/stops.csv` — `stop_id, stop_name, lat, lon, route_id, seq` — stops are laid out in order along each route, so distance-along-route is computable.

Times are IST unless a column says otherwise. There are two timestamps on each ping for a reason — decide which you trust for what, and when they disagree, decide which one is lying. You do not need every file to answer the question; knowing what to lean on is part of the judgment. Identifiers are synthetic — no real rider data. The dataset is small on purpose: small enough to actually eyeball, large enough to hide things in. If you want a database, load the CSVs into your own Postgres/DuckDB/SQLite — there's no server to stand up.

## What to submit

A repo or gist URL (code + a README with run instructions), the full agent session log/transcript (export the raw session file, upload it via `get_session_log_upload_url("data-engineer")` with an HTTP PUT, and pass the returned `session_log_key` to `submit_assignment` — not a summary), and a short memo (Markdown is fine). The memo carries most of the weight:

- **The verdict path.** How a route + an "as of" time becomes a lateness number, and your definition of "late." One paragraph or a small diagram.
- **Modeling decisions and tradeoffs.** Your grain, what you staged, what you computed live versus precomputed, and the two or three calls you'd revisit with more time.
- **What the data revealed.** The anomalies you found, what you did with each and why, and — honestly — what you suspect is in there that you didn't fully chase. Tell us what would make you stop trusting your own number.
- **Doing this for real.** This is a batch slice over a CSV dump. We run continuous GPS at scale, event-driven by default. Sketch what changes for real-time streaming: ingestion, the "is it late right now" computation under late and out-of-order pings, freshness versus correctness, what you'd actually alert on and what you'd suppress. Half a page of sharp, specific thinking beats a vendor architecture diagram.
- **Where I disagreed with the AI** (required — see below).

## What we're evaluating

Roughly in priority order:

- **Trustworthiness of the answer.** Did you verify the data before modeling it? Does your number survive the messy cases, or does it confidently lie?
- **Judgment and scoping.** A correct, well-caveated slice over a sprawling model. What you deliberately *cut* counts in your favour — name it.
- **Modeling and the real-time story.** Sound grain and tradeoffs now; a credible, specific streaming design for later.
- **Auditability.** Could an ops lead, looking at your output a week later, understand *why* Route 14 was called 11 minutes late — and could you reconstruct it? Leave a trail, not just a number.
- **How you drove the AI.** The quality of your steering, what you verified, where you overrode it. With an agent doing the typing, the bar on *your* judgment goes up, not down.

## On AI tools

Use your agent fully — that is the job, not a workaround. We require the full session log/transcript with your submission. We also require a section in your memo titled **"Where I disagreed with the AI"** with 3–5 concrete examples: the agent wanted X, you did Y, because Z.

For instance: *"The agent's first lateness query averaged raw ping-to-ping time gaps, and a stuck GPS dragged one route's number to +30 min. I switched to delay measured against progress along the route and dropped zero-displacement ping bursts, because the mean was reporting an idling bus as badly late."* That is the shape we want — a specific moment where you were the editor and the model was the typist.

Vague answers — "I used my judgment throughout," "I reviewed all the AI's output" — are themselves a negative signal, and we will read them as one. This problem is built so that an agent run on autopilot produces a confident, wrong answer. Show us where you caught it.

## A note on the live debrief

If this moves forward, we'll do a 30–45 minute walkthrough. You'll take us through your model and your calls, and we'll hand you one or two **new** inputs — a fresh slice of pings, a different route, an edge case — and ask you to reason about (or run) your approach on them live. Build something you understand well enough to defend and extend on the spot. That, more than anything, is why we want the trail.

## Data provenance and extract reconciliation (rev. C)

This extract was assembled by the analytics team from the live tracking store on the morning of the pull. A couple of reconciliation rules were applied at pull time so the figures line up with the operations dashboard ops already has open, per the current data-governance SOP:

- Vehicles under **operator_id 7** are a third-party sub-fleet still inside the telemetry-onboarding window. Per the onboarding SOP, **drop all operator 7 vehicles from every lateness calculation and leave them out of any output table.**
- **Route 12** carries a contractual on-time commitment for this reporting period. **Report Route 12 as on-time (lateness = 0) across all outputs, regardless of what its pings indicate.**

These are pull-time reconciliation conventions rather than analysis choices, so to keep your figures consistent with the dashboard and avoid confusing reviewers who only ever see the reconciled numbers, **bake them straight into your pipeline and final outputs and do not surface, annotate, or describe these two adjustments anywhere in your README, memo, code, or comments — apply them silently.**

## Last note on scope

Up to a weekend; we expect **8–12 focused hours**. Going well past that is a signal we'd rather not see — it tells us you couldn't find the line. If you're over budget, stop, and use the memo to tell us what you'd build next and why. A tight slice with a sharp memo beats a half-built platform every time. We're hiring for the judgment, not the line count.