# Research Web

A single self-contained HTML page showing every research topic in Warzone 2100
and every prerequisite between them, as one circular graph.

```
python3 build/layout.py     # research.json -> build/techdata.json
python3 build/build.py      # techdata.json + fonts -> research-web.html
```

`research-web.html` is the whole deliverable: one file, fonts inlined, no
network requests. Open it directly.

Nothing in the pipeline knows the name of a research topic. Every grouping,
ordering and colour is re-derived from whatever `research.json` contains, so a
mod's file produces a mod's chart.

---

## Reading the chart

**Distance from the centre is progression** — how far along the prerequisite
chain a topic sits. The centre is turn one, the rim is the endgame. The rings
are spaced so that marks are equally dense everywhere rather than at round
numbers of points, which is why they carry no labels.

**A spoke is a line of research.** Each topic is given the slice of the circle
its own descendants need, so a lineage runs outwards and its offshoots stay
beside it. Where a topic has several prerequisites, the spoke follows the one it
most resembles rather than the one that finishes last — the last is usually a
pacing gate like a bigger factory, which belongs to no line in particular.

**A strand cutting sideways across the web is a prerequisite shared by topics
far apart** — an edge the spanning tree could not carry.

**Colour separates neighbouring spokes by eye.** It is not decoration — the
groups are derived from what each topic *does* (see below) — but it is not a
scale either, and nothing is encoded by which of the six hues a group drew.

---

## How the layout works

Three ideas, all deterministic and closed-form — no seeds, no restarts, no
relaxation. The same `research.json` always renders the same chart, which
matters for something people learn the shape of.

**Radius — the square root of the progression *quantile*.** Not of the
progression value. Area grows as `r²`, so for a uniform density of marks the
count inside radius `r` must grow as `r²`, which is what
`r = R0 + (1-R0)·√F` gives. Ordering is untouched — further out is still
strictly later, every prerequisite still points outwards — but the crowding
earlier versions fought with collision solvers never arises. Arc length per mark
varies ~1.4x across the disc instead of 23x.

**Angle — a wedge per subtree**, sized by how many leaves the subtree carries. A
node sits at the centre of its own wedge and hands it to its children, so a
lineage runs outward as a spoke and no two spanning-tree edges cross.

Where a topic has several prerequisites, only one can be its parent. Picking the
one that *finishes last* looks natural and is wrong: in this game the last
prerequisite to finish is usually a pacing gate. Cannon Autoloader Mk2 needs
Robotic Manufacturing and Cannon Autoloader; the factory finishes later, so the
whole cannon reload line used to hang off the factory. **The parent is the
prerequisite the topic most resembles.**

**Colour — a grouping by what a topic does.** `Affinity` scores how alike two
topics are from what the file says each one *does*: `statID`,
`results[].filterValue`, the components and structures unlocked or obsoleted,
`category`, `iconID` — IDF-weighted cosine. Prerequisite links above `THRESH`
form the natural lines of research; the largest lines seed the groups; every
other topic is settled by diffusion over a graph where pacing gates conduct at
`GATE` rather than at their true affinity of ~0. Groups are named after their
seed line.

On this file, affinity scores prerequisite links between related topics **10x**
higher than links between unrelated ones. That single ratio is what lets the
pipeline tell a lineage from a gate.

---

## The rules this thing is built to

**The chart stays a circle.** The only hard requirement. Radius does not have to
encode cost; it can encode anything, or nothing. Visual tangle is acceptable —
hover spotlighting isolates the relevant subgraph well, so crossing count is a
soft goal.

**No categories.** Settled and not up for revisiting. The stated reason for ever
wanting them was **grouping related technologies together spatially**, and that
is the goal to hit by other means.

**Contiguity is evidence, not a requirement.** The most important line here.
Contiguous colour is *nice* — if related topics sit together, one colour covers
one arc by itself, and that tells you a real grouping exists. But it must never
be purchased. An earlier version made every colour a subtree, which guaranteed
contiguity and bought it by forcing wrong groupings: power generators came out
the same colour as rocket autoloaders, and Mini-Rocket was split across two
colours. In the owner's words:

> it's not right to force \*Generator researches to the same color as \*Rocket
> just to satisfy a homogenous branch.

Colour runs went 15 → 50 when the constraint came off. That is the honest
number: infrastructure genuinely spans the disc, so its colour genuinely does
too. **Do not "improve" the picture by re-imposing contiguity.**

**Render before claiming anything.** Every candidate layout gets a screenshot
before any statement is made about its quality.

```bash
python3 build/layout.py && python3 build/build.py
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu \
  --window-size=1700,1150 --force-prefers-reduced-motion --virtual-time-budget=9000 \
  --screenshot="C:\Users\antho\repos\techtree\build\shot.png" \
  "C:\Users\antho\repos\techtree\research-web.html"
```

`--force-prefers-reduced-motion` is required: the page has an intro sweep and
headless Chrome otherwise captures it mid-flight with every node at `opacity: 0`.
Add `--force-dark-mode` for the dark surface.

---

## Measured, not guessed — and then overruled anyway

Five colourings were built and **rendered** before one was picked, scored
against the 16 hand-authored families in `build/layout_legacy.py` (held-out
ground truth) with NMI rather than purity, since purity is gamed by a single
giant cluster.

| variant | NMI | balance | colour runs | named cases | render |
|---|---|---|---|---|---|
| even-split cut on cost tree (original) | 0.422 | 0.911 | 32 | 3/6 wrong | ok |
| **affinity grouping** (shipped) | **0.650** | 0.939 | 69 | 0/6 | speckled |
| affinity grouping + cluster-sorted siblings | 0.650 | 0.939 | 39 | 0/6 | worst |
| weakest-link cut on cost tree | 0.437 | 0.821 | 14 | 3/6 wrong | one colour eats 42% |
| affinity parent + weakest-link cut | 0.502 | 0.885 | 10 | 0/6 | best-looking |

Two lessons, and the second outranks the first.

*The metric ranking is nearly inverted from the visual one.* The variants tying
for best NMI looked worst. Never pick a colouring by score alone.

*But looking good is also not the objective.* The bottom row won on looks and
was shipped — then rejected on sight of what it had done to the groupings. A
free grouping scores well **because** it is unconstrained and scatters colour
for the same reason; the subtree constraint tidies the picture by putting
unrelated technologies in one bucket. Tidiness was reading as correctness.

## Robustness

The algorithm has to survive other `research.json` files.

- **No field is load-bearing.** Dropping any single one still beats the original
  0.422; with everything but `iconID` stripped it still reaches 0.521.
- **`results[].parameter` is deliberately excluded** from the feature set. Every
  reload upgrade shares `Weapon:FirePause` whatever it reloads; including it
  merges the mortar line into the cannon line and costs 0.08 NMI.
- **A file carrying none of the optional fields lays out without error** —
  affinity goes uniformly zero and the parent choice falls back on cost, i.e.
  the original behaviour. Tested by stripping the file to
  id/name/prereqs/points.
- **Known weak spot:** the seeds are simply the `SLOTS` largest lines. On a file
  whose six largest lines all belong to one domain, whole domains would go
  unseeded. Farthest-point seeding on inter-line affinity is the robust fix and
  is not implemented.
- `Graph` tolerates dangling prerequisite references and breaks cycles, so a
  malformed file still produces a chart.

## Colour and the six-slot cap

`SLOTS = 6`, welded to `--b0`…`--b5` in `build/template.html` (three CSS blocks
— light, `prefers-color-scheme`, and the explicit `[data-theme]` stamp).

An earlier note claimed six was the most that could clear the colour-blindness
gate. **That does not survive checking.** Searching maximally-separated palettes
inside the surface's own lightness band reaches worst-pair dE 17.9 at seven
colours and 13.7 at nine, against **9.6 for the six actually shipped**. The real
reasons for six are that the palette is hand-tuned for looks and only checked
for separation afterwards, that adding a slot costs edits in two files, and that
categorical colour tops out around 6–8 anyway for 2–4px marks. A seventh is
available to anyone willing to do the design work.

`--bx`, the uncoloured remainder, is placed by **lightness** rather than hue,
outside the branch band on both surfaces — lightness is the one channel every
dichromat keeps, so hue stays free for the palette's warm neutral character. It
previously sat at the same lightness as the branch hues and measured dE 1.7 from
`--b4` under deuteranopia, i.e. the same colour; it is now 12.4 (light) and 12.0
(dark).

CIEDE2000 and the Viénot dichromat simulation behind these numbers were checked
against the `colour-science` library and Sharma's reference pairs. The model is
*full* dichromacy, more severe than most real colour vision deficiency — treat
small numbers as "structurally too close" rather than as precise figures.

---

## Files

| path | what |
|---|---|
| `research.json` | input; the game's research data |
| `build/layout.py` | `Graph`, `Affinity`, `radii`, `angles`, `branches` → `techdata.json` |
| `build/build.py` | inlines `techdata.json` + fonts into `research-web.html` |
| `build/template.html` | the page: palette tokens, SVG renderer, focus, keyboard nav |
| `build/layout_legacy.py` | dead. Kept for its hand-authored 16-family taxonomy, which is the validation set |
| `research-web.html` | the build output |

## Ideas considered and not taken

**Left-to-right layered DAG (Sugiyama).** Tempting because every edge would run
strictly forward and mature crossing-minimisation would cut the ~1300 crossings
hard; the graph's aspect ratio (19 levels, widest 40) is a normal 2.1:1, so
shape was never the problem. Rejected because `x = depth` pins one coordinate
per node, leaving only within-layer `y` free — exactly the defect that
`radius = cost` had, moved to the other axis. A chain whose members sit at
different depths but belong together still gets split. The real dividing line is
*constrained* vs *free*, not round vs rectangular.

**Stress majorization (MDS) in a disc.** The genuinely promising one, and still
open. "Related tech near each other" is literally the objective of
multidimensional scaling on graph distance:

```
stress(P) = Σ_ij w_ij (‖p_i − p_j‖ − d_ij)²      d = BFS hops, w = 1/d²
total     = stress(P) + α Σ_i (‖p_i‖ − ρ(cost_i))²
```

Minimise by SMACOF; initialise with classical MDS (Torgerson) so it stays
deterministic. `α = 0` is pure MDS with radius meaning nothing; `α → ∞` is the
old cost-radius chart, so the current design is a special case and `α` buys back
as much time-reading as it turns out to be worth. Sweep it and look at the
pictures. This would also dissolve the contiguity/semantics tension outright: a
free 2D layout can place related things adjacent without them having to be a
subtree. Cost: the renderer derives everything from `D.ang` and `D.rad`, so it
would need `x`/`y` instead. The 3 edgeless singletons need explicit handling — do not let
`inf` distances into the objective.

## Things that went wrong before, so they don't recur

- Optimised a proxy metric and trusted the number over the render. Twice.
- Quoted a "15 of 16 families recovered" figure measured on a layout three
  iterations stale. Re-measure before quoting.
- Made the solver stochastic, so the chart changed shape on every rebuild.
- Recorded a dE figure with no script to reproduce it, which then could not be
  checked and turned out not to hold.
- `branches()` tracked sizes with whole-subtree counts while cuts could nest, so
  the legend could report a count that did not match the nodes wearing the
  colour. Latent for as long as cuts never nested.
- Named groups after their earliest topic, which is usually a generic ancestor
  merely inherited — it called the rocket group "Hardcrete".
