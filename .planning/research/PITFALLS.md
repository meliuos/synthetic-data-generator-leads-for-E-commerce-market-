# Pitfalls Research

**Domain:** Real-time event tracking and heatmap visualization system
**Researched:** 2026-04-14
**Confidence:** HIGH (coordinate/ClickHouse/Kafka pitfalls verified against official docs and multiple sources), MEDIUM (SPA/GDPR/Streamlit pitfalls verified against multiple community sources)

---

## Critical Pitfalls

### Pitfall 1: Coordinate System Confusion — clientX vs pageX vs offsetX

**What goes wrong:**
The tracker captures `clientX`/`clientY` (viewport-relative) but the heatmap renderer needs document-relative coordinates. When any scroll has occurred, these values diverge. Clicks appear shifted upward on the rendered heatmap by exactly the scroll distance at capture time. This looks subtle in testing (no scroll) but breaks in production (real users scroll).

**Why it happens:**
`clientX` and `clientY` are the easiest event properties to grab and look correct in a zero-scroll test. The difference only surfaces when you overlay points onto a full-page screenshot and the page is not at the top.

**How to avoid:**
Always capture `pageX = clientX + window.scrollX` and `pageY = clientY + window.scrollY` at capture time. Store both values — `clientX`/`clientY` for viewport-relative analysis (above-the-fold), `pageX`/`pageY` for full-page heatmap rendering. Validate by recording a long page, scrolling to 50%, clicking, and verifying the stored `pageY` matches visual position on the document.

**Warning signs:**
- Heatmap dots cluster correctly near the top of the page but drift downward from expected position on lower sections
- Test clicks at document top match perfectly; test clicks after scroll are off by exactly `window.scrollY`
- Screenshots of heatmap overlays look fine for users who never scrolled

**Phase to address:**
JS tracker implementation phase (capture layer). This must be validated before any data is stored — corrupted coordinates cannot be retroactively corrected without raw event replay.

---

### Pitfall 2: devicePixelRatio and Zoom Level Double-Scaling

**What goes wrong:**
On high-DPI (Retina) displays, `devicePixelRatio` is 2 or 3. If you multiply captured coordinates by `devicePixelRatio` to convert to physical pixels AND the browser has also scaled the layout for the display, coordinates are doubled. Heatmap points land in the wrong quadrant.

**Why it happens:**
CSS pixels are the correct coordinate space for layout. `devicePixelRatio` is relevant only when drawing to `<canvas>` at native resolution. Developers mix these two concerns when trying to "normalize" coordinates across devices.

**How to avoid:**
Never multiply `pageX`/`pageY` by `devicePixelRatio`. Store all coordinates in CSS pixels. The viewport width at capture time (`window.innerWidth`) is already in CSS pixels. Normalize coordinates as percentages of `document.body.scrollWidth` and `document.body.scrollHeight` to make them resolution-independent. At render time, translate percentages back to pixel positions on the screenshot canvas.

**Warning signs:**
- Heatmap points appear in roughly the right region but offset by a factor of ~2 on mobile or Retina screenshots
- Heatmap looks correct on a 1x display but is wrong on a MacBook or iPhone
- `devicePixelRatio` appears anywhere in coordinate calculation code

**Phase to address:**
JS tracker implementation phase. Write a unit test that simulates `devicePixelRatio=2` and verifies coordinates are unchanged in CSS pixel space.

---

### Pitfall 3: ClickHouse Hammered With Per-Event Inserts

**What goes wrong:**
The Kafka consumer inserts one row per consumed event. At modest scale (100 concurrent users, mouse movement at 100ms intervals), this means 1,000 inserts/second. Each small insert creates a new immutable part on disk. Background merge processes fall behind, CPU spikes, and ClickHouse throws `Too many parts` errors, making the database unavailable for both inserts and queries.

**Why it happens:**
The naive pattern is: consume from Kafka → parse event → `INSERT INTO events VALUES (...)`. This works for 10 events/second. It falls apart at 100+.

**How to avoid:**
Buffer events in the consumer before inserting. Two valid approaches:
1. **Time-based micro-batching**: Accumulate events for 1–5 seconds in memory, then insert a batch. Target 1,000–100,000 rows per INSERT.
2. **ClickHouse async inserts**: Enable `async_insert=1, wait_for_async_insert=1` at the connection level. ClickHouse buffers on the server side and batches automatically. Use `wait_for_async_insert=1` — the alternative `wait_for_async_insert=0` is fire-and-forget with no error feedback, which is dangerous.

For an academic demo, async inserts are the simplest option. For production, micro-batching with acknowledgment gives more control.

**Warning signs:**
- ClickHouse logs show `DB::Exception: Too many parts`
- Query latency increases over time as parts accumulate
- INSERT throughput drops while CPU stays high (constant merging)
- Consumer inserts single-row in a tight loop

**Phase to address:**
Kafka consumer / ClickHouse integration phase. Benchmark insert strategy before building heatmap computation on top of it — if this is wrong, the entire pipeline is unreliable.

---

### Pitfall 4: Mouse Movement Event Flood

**What goes wrong:**
`mousemove` fires at the display refresh rate — up to 60 events/second per user. For a 30-minute session with a moderately active user, this generates ~108,000 movement events. Unthrottled, this overwhelms: the Kafka producer queue, the consumer's insert buffer, and ClickHouse storage (mouse movement data alone grows to gigabytes quickly).

**Why it happens:**
Tracking mouse movement feels necessary for move heatmaps, but raw `mousemove` is captured without any rate limiting during initial implementation.

**How to avoid:**
Throttle `mousemove` capture to 10 events/second (100ms interval) minimum — Hotjar uses this exact rate. For move heatmaps specifically, 4 events/second (250ms) is sufficient resolution. Implement throttling in the JS tracker using `requestAnimationFrame` or a timestamp check (`if (Date.now() - lastCapture < 100) return`). Never use `setInterval`-based throttling — it creates drift. Store only the final position when the mouse stops moving (trailing-edge throttle).

Additionally, consider whether move heatmaps are in scope. Click heatmaps (low volume) provide more actionable insight. Move heatmaps require 10–20x more storage and computation for marginal gain in an academic project.

**Warning signs:**
- Kafka topic lag grows immediately when a user session starts
- Storage usage exceeds expectations within hours of starting the tracker
- ClickHouse query on movement data takes >10 seconds at modest session count
- Network tab shows hundreds of beacons/second from the tracked page

**Phase to address:**
JS tracker implementation phase. Set throttle thresholds before any load testing.

---

### Pitfall 5: SPA Navigation Breaks Heatmap Bucketing

**What goes wrong:**
In a single-page application (React, Vue, etc.), navigating between routes does not trigger a full page reload. If the tracker only listens to `window.load` or uses `document.location.href` at capture time, all click events across all routes get merged into a single heatmap for the initial URL. A click on "Checkout" button is mixed with a click on "Hero banner" because both happened on `https://app.com/`.

**Why it happens:**
The tracker captures `window.location.href` on load and assumes it is stable for the session. SPAs change location using the History API without dispatching events that most trackers listen to by default.

**How to avoid:**
Intercept `history.pushState` and `history.replaceState` in addition to listening for the `popstate` event. Update the captured URL on every navigation. Capture the current URL at the moment of the event, not at session start:

```js
// Capture URL at event time, not at session start
const capturedUrl = window.location.pathname + window.location.search;
```

Also hash the normalized URL + viewport width together as the "page identity" for heatmap bucketing.

**Warning signs:**
- All clicks on an SPA accumulate in one heatmap regardless of page
- Moving between routes in a demo shows clicks bleeding across pages
- URL field in stored events is always the entry URL, never subsequent routes

**Phase to address:**
JS tracker implementation phase. Test with a multi-route application before integrating with storage.

---

### Pitfall 6: ClickHouse Sorting Key Chosen for Convenience, Not Query Patterns

**What goes wrong:**
The events table is created with `ORDER BY (event_id)` or `ORDER BY (created_at)` because those seem natural. Heatmap queries filter by `(page_url, event_type, session_date)`. ClickHouse must do a full table scan for every heatmap computation because the sorting key does not match filter columns. Queries that should take milliseconds take minutes.

**Why it happens:**
Developers coming from RDBMS background treat `ORDER BY` in ClickHouse as a cosmetic choice. In MergeTree, it is the primary index — the single most important performance decision.

**How to avoid:**
Design the sorting key around actual query access patterns. For heatmap queries:

```sql
ORDER BY (page_url, event_type, toDate(timestamp), session_id)
```

Rules:
- Low-cardinality columns first (filters that eliminate large chunks)
- High-cardinality columns (`session_id`, `event_id`) last
- Timestamp near the end of the key (used for range scans, not point lookups)
- Do NOT use UUID/GUID as the first key column — this destroys compression and granule efficiency

Additionally, avoid `Nullable` types for all analytics columns. Use empty string (`''`) or zero as sentinel values. `Nullable` adds a separate null-bitmap column and slows queries measurably.

**Warning signs:**
- `EXPLAIN` on a heatmap query shows `Rows read: [total rows in table]`
- Query time grows linearly with total event count rather than staying flat
- ClickHouse `system.query_log` shows `read_bytes` matching full table size for filtered queries

**Phase to address:**
ClickHouse schema design phase, before any data ingestion begins. Changing the sorting key requires dropping and recreating the table.

---

### Pitfall 7: GDPR — Tracking Before Consent and Storing Raw IPs

**What goes wrong:**
Two distinct violations compound each other:
1. The JS snippet loads and starts capturing events on page load, before the user sees or accepts a consent banner. Every event captured before consent is a GDPR violation.
2. IP addresses are stored in ClickHouse as part of the event payload. IP addresses are personal data under GDPR Article 4(1). Storing them without legal basis or a declared retention policy is non-compliant.

**Why it happens:**
Developers focus on making the tracker work correctly before thinking about consent lifecycle. IP addresses appear in server-side request headers and get logged automatically.

**How to avoid:**
1. **Consent gate**: Do not initialize the tracker (do not load the snippet or call `RudderStack.load()`) until consent is granted. Store consent state in a cookie or localStorage and check it before any tracking code runs.
2. **IP anonymization**: Either strip IP addresses before they reach Kafka (at the collection endpoint), or store only the first three octets (`192.168.1.x` → `192.168.1.0`). Better: use a server-side collection endpoint that drops the IP and instead stores a hashed, salted session identifier.
3. **Academic exception**: For a GL4 academic project on a controlled demo environment, GDPR does not technically apply (no real user data). However, demonstrating awareness of these issues during the thesis defense is a differentiator. Implement IP masking in the pipeline as a "privacy by design" demonstration.

**Warning signs:**
- Tracker initialization happens outside any consent callback
- IP address column exists in the events table with real addresses
- No consent banner or consent state management in the tracked demo page

**Phase to address:**
JS tracker implementation phase (consent gating) and ClickHouse schema design phase (data model for IP handling).

---

### Pitfall 8: Kafka Consumer Rebalance Storm When Scaling

**What goes wrong:**
Adding more consumer instances to reduce lag triggers frequent group rebalances. During each rebalance, all consumers in the group stop processing. If consumer startup is slow or if per-message processing time is high, rebalances keep interrupting work, lag increases instead of decreasing, and duplicate events are written to ClickHouse on every rebalance.

**Why it happens:**
The intuitive fix to "consumer is too slow" is "add more consumers." This works only when the partition count supports it and when consumers rejoin quickly. With heavyweight ClickHouse inserts per message, heartbeat timeouts trigger rebalances under load.

**How to avoid:**
- Set Kafka topic partition count = maximum expected consumer parallelism (set this upfront, partitions cannot be reduced later)
- Use micro-batching (pitfall 3 mitigation) to make per-message work fast and heartbeats reliable
- Tune `max.poll.interval.ms` to be larger than your worst-case batch processing time
- For an academic demo: use a single consumer with micro-batching rather than multiple consumers — simpler and avoids rebalance issues entirely

**Warning signs:**
- Consumer logs show repeated `Assigned partitions`, `Revoked partitions` in quick succession
- Consumer lag grows after adding consumers, not shrinks
- Duplicate events appear in ClickHouse at session boundaries

**Phase to address:**
Kafka consumer / pipeline integration phase.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store raw JSON in ClickHouse `String` column | No schema needed, flexible | Query-time parsing is 10–100x slower; no compression benefit | Never — define schema upfront |
| One Kafka topic for all event types | Simple setup | Heatmap consumer must deserialize all events; can't scale click processing independently of mouse movement | Acceptable for academic MVP; split topics for production |
| Skip scroll position in event payload | Simpler capture | Cannot reconstruct full-page coordinates; scroll heatmaps are impossible | Never — scroll offsets are cheap to capture |
| Use `ReplacingMergeTree` for deduplication | "Automatic" deduplication | Deduplication is eventual — SELECTs before merge return duplicates unless using `FINAL` keyword (slow) | Never for analytics — accept at-least-once and deduplicate at query time with `LIMIT 1 BY event_id` |
| `wait_for_async_insert=0` in ClickHouse | Faster apparent inserts | Silent data loss — no error feedback on insert failure | Never |
| Capture `mousemove` without throttling | Complete movement data | Storage explosion, pipeline overload within minutes | Never — always throttle |
| Initialize tracker before consent check | Simpler code | GDPR violation (even in demo context, it demonstrates bad practice) | Only in isolated localhost dev with no real users |

---

## Integration Gotchas

Common mistakes when connecting components.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| RudderStack SDK → Kafka | Using RudderStack cloud data plane (sends to RudderStack servers) instead of self-hosted | Configure `dataPlaneUrl` to point to your own data plane endpoint; otherwise events never reach your Kafka |
| Kafka → ClickHouse consumer | Using auto-commit offset before insert completes | Commit offset only after successful ClickHouse insert; otherwise events are lost on consumer crash |
| JS tracker → RudderStack SDK | Calling `track()` with coordinates as floats with 15 decimal places | Round to 2 decimal places at capture — ClickHouse stores floats fine but the payload size bloats Kafka messages unnecessarily |
| ClickHouse → Python heatmap | Pulling all raw events for a page into Python memory | Use ClickHouse-side aggregation (`countMerge`, binned coordinates) before fetching — pull a 200x200 grid, not 50,000 raw points |
| Python → Streamlit | Recomputing heatmap on every Streamlit interaction (widget change) | Cache heatmap computation with `@st.cache_data` with a TTL; Streamlit reruns the entire script on every user interaction |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full table scan for heatmap query | Query time grows with total event count | Correct sorting key `(page_url, event_type, toDate(timestamp))` | From the first million events |
| Fetching raw events to Python for heatmap | Python OOM, slow renders | Aggregate in ClickHouse; send binned grid to Python | ~50,000 events per page |
| Unthrottled mousemove capture | Kafka lag builds within seconds, ClickHouse part explosion | Throttle to 100ms minimum at capture | From first real user session |
| Single Kafka partition | Cannot parallelize consumption | Set partition count = expected consumer parallelism upfront | At 2+ consumer instances |
| Streamlit reruns on every filter change | Each filter change triggers ClickHouse query | `@st.cache_data` with TTL, aggregate queries | At 3+ concurrent Streamlit users |
| Storing coordinates as FLOAT64 | Wasted precision for pixel coordinates | Use `UInt16` for x/y (max 65535, fine for any viewport) and `UInt32` for scroll depth | Schema creates 2x storage overhead from day one |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing raw IP addresses in ClickHouse | GDPR Article 4(1) violation; IP is personal data | Anonymize at collection endpoint (strip last octet or hash with session salt) |
| No origin validation on collection endpoint | Any site can send events to your pipeline, polluting data | Validate `Origin` header; reject events from unauthorized domains |
| Tracker snippet injectable via XSS | Attacker modifies captured coordinates or injects fake sessions | Serve snippet from controlled CDN; validate event schema at collection endpoint (reject events with unexpected fields) |
| session_id is sequential integer | Session enumeration attack — attacker can download all sessions | Use UUID v4 for session identifiers |
| ClickHouse exposed directly to Streamlit without query firewall | Streamlit users can trigger arbitrary-cost queries | Use a read-only ClickHouse user for Streamlit; restrict to specific tables |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Merging click data from all viewport widths | Heatmap shows smeared clusters — mobile and desktop clicks are in different positions | Segment heatmaps by viewport width bucket: mobile (<768px), tablet (768–1024px), desktop (>1024px) |
| Scroll heatmap uses raw % scrolled | Users who passively left page "at 80% scroll" inflate numbers | Differentiate active scroll (velocity > 0) from passive abandonment; track time-spent per scroll zone |
| Rage click detector fires on double-click | Double-clicking a button triggers "rage click" alert | Threshold: 3+ clicks within 2 seconds, same target element ±10px, not native dblclick event |
| Heatmap shows "nothing was clicked" on low traffic pages | Data interpreted as low engagement, but sample size is < 200 sessions | Show sample size warning; require minimum 200 sessions before displaying heatmap |
| Heatmap rendered without page screenshot context | Dots with no background — uninterpretable | Capture page screenshot (or DOM snapshot) alongside events; render heatmap as overlay |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **JS Tracker**: Captures clicks — but does it capture `pageX`/`pageY` (with scroll offset), not just `clientX`/`clientY`? Verify by clicking after scrolling 500px.
- [ ] **JS Tracker**: Handles SPA route changes? Navigate to a sub-route and verify the stored `page_url` updates.
- [ ] **Kafka Pipeline**: Events appear in topic — but has consumer offset commit been verified as post-insert (not pre-insert)? Kill consumer mid-batch and confirm no loss.
- [ ] **ClickHouse**: Events are inserted — but what is the `ORDER BY` clause? Does it match actual heatmap query filters?
- [ ] **Heatmap Computation**: Python generates a heatmap image — but is it segmented by viewport width? A 320px-wide mobile click and a 1920px-wide desktop click should NOT appear on the same heatmap.
- [ ] **Streamlit Dashboard**: Displays heatmap — but does it show the page screenshot as background context? Dots without context are uninterpretable.
- [ ] **Data Volume**: Mouse movement is captured — but at what rate? Open the Network tab and count beacons per second.
- [ ] **Rage Clicks**: Detected and displayed — but what is the detection threshold? Is it differentiated from legitimate double-clicks?

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong coordinate system in production data | HIGH | Raw events must be replayed if original `clientY` and scroll offsets were both stored; if only `clientY` stored, data is unrecoverable for scrolled sessions |
| ClickHouse wrong sorting key | HIGH | Drop and recreate table; reingest from Kafka (requires sufficient retention period on Kafka topic — set 7-day retention) |
| ClickHouse part explosion from small inserts | MEDIUM | Run `OPTIMIZE TABLE events FINAL` to force merge (slow, one-time); fix insert strategy going forward |
| Mouse movement data flood fills disk | MEDIUM | Truncate movement event partition for affected time range; reduce throttle interval and redeploy tracker |
| SPA URL not updating — all clicks on one page | MEDIUM | Data already stored is corrupted (mixed pages); fix tracker and restart collection; old data unusable for per-route heatmaps |
| Consumer lag from no batching | LOW | Stop consumer, add micro-batching logic, restart; no data loss if offsets were committed correctly |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| clientX vs pageX coordinate confusion | JS tracker implementation | Click at document bottom after scrolling; verify `pageY > clientY` in stored event |
| devicePixelRatio double-scaling | JS tracker implementation | Verify no DPR multiplication in coordinate code; test on simulated Retina display |
| ClickHouse small insert hammering | Kafka→ClickHouse consumer phase | Benchmark: insert 10,000 events; verify single-digit number of new parts in `system.parts` |
| Mouse movement flood | JS tracker implementation | Count events/second in Network tab with throttle active; should be ≤10/sec |
| SPA route change blindness | JS tracker implementation | Navigate 3 routes; verify 3 distinct `page_url` values in Kafka topic |
| Wrong ClickHouse sorting key | ClickHouse schema design phase | `EXPLAIN` on heatmap query; verify rows read << total rows |
| GDPR — pre-consent tracking | JS tracker implementation | Verify tracker does not initialize until consent callback fires |
| GDPR — raw IP storage | ClickHouse schema design phase | Verify `ip_address` column stores masked value or is absent from schema |
| Kafka consumer rebalance storm | Pipeline integration phase | Add 2nd consumer instance; verify lag decreases, not increases |
| Rage click false positives | Event classification phase | Manually double-click a button; verify it is NOT flagged as rage click |
| Scroll depth false high engagement | Heatmap computation phase | Verify tracker pauses when tab loses focus (`document.visibilityState`) |
| Viewport-mixed heatmap | Heatmap computation phase | Verify query filters by viewport width bucket before aggregation |

---

## Sources

- ClickHouse insert strategy official docs: https://clickhouse.com/docs/best-practices/selecting-an-insert-strategy (HIGH confidence)
- ClickHouse schema design for observability: https://clickhouse.com/docs/use-cases/observability/schema-design (HIGH confidence)
- ClickHouse AI schema mistakes blog: https://clickhouse.com/blog/ai-generated-clickhouse-schemas-mistakes-and-advice (HIGH confidence)
- FullStory heatmap accuracy problems: https://www.fullstory.com/blog/what-are-web-heatmaps-how-do-they-work-pros-cons-alternatives/ (MEDIUM confidence)
- SPA heatmap pitfalls (FullSession): https://www.fullsession.io/blog/spa-heatmaps-route-changes-view-identity-validation/ (MEDIUM confidence)
- Kafka consumer rebalance storms: https://www.michal-drozd.com/en/blog/kafka-consumer-rebalance-storm/ (MEDIUM confidence)
- Kafka consumer lag guide (Last9): https://last9.io/blog/fixing-kafka-consumer-lag/ (MEDIUM confidence)
- GDPR analytics compliance 2026: https://webflow.trackingplan.com/blog/privacy-compliance-for-analytics-complete-guide-2026-en (MEDIUM confidence)
- Scroll depth false confidence: https://ceaksan.com/en/why-scroll-depth-tracking-fails (MEDIUM confidence)
- Streamlit large dataset limitations: https://discuss.streamlit.io/t/very-large-datasets/3168 (MEDIUM confidence)
- Rage click false positives (PostHog issue tracker): https://github.com/PostHog/posthog-js/issues/2487 (MEDIUM confidence)
- devicePixelRatio viewport zoom interaction (W3C RICG): https://www.w3.org/community/respimg/2013/04/06/devicenormalpixelratio-proposal-for-zoom-independent-devicepixelratio-for-hd-retina-games/ (MEDIUM confidence)
- MouseEvent coordinate space (Mozilla Bugzilla): https://bugzilla.mozilla.org/show_bug.cgi?id=1753836 (HIGH confidence)

---
*Pitfalls research for: real-time event tracking and heatmap visualization system*
*Researched: 2026-04-14*
