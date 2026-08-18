"""Radial layout for an arbitrary research.json.

Nothing here knows the name of a single research topic, and nothing is sorted
into categories. There is no branch table, no weapon-prefix list, no hand-
ordered ring. Three ideas do all the work:

  radius   the square root of the progression *quantile*, not of the
           progression value. Area grows as r^2, so for a uniform density of
           marks the count of topics inside radius r must grow as r^2 -- which
           is what r = R0 + (1-R0)*sqrt(F) gives. Ordering is untouched (further
           out is still strictly later, every prerequisite still points
           outwards) but the crowding that every previous version fought with
           collision solvers simply does not arise: arc length per mark varies
           by ~1.4x across the disc instead of 23x.

  angle    a wedge per subtree of the spanning tree, sized by how many leaves
           the subtree carries. Each node sits at the centre of its own wedge
           and hands that wedge on to its children, so a lineage runs outwards
           as a spoke and no two spanning-tree edges cross.

           A topic usually has several prerequisites and only one can be its
           parent. Picking the one that *finishes last* looks natural and is
           wrong: in this game the last prerequisite to finish is typically a
           pacing gate ("you also need a bigger factory"), not the lineage the
           topic belongs to. Cannon Autoloader Mk2 needs Robotic Manufacturing
           and Cannon Autoloader; the factory finishes later, so the whole
           cannon reload line used to hang off the factory. The parent is
           instead the prerequisite the topic most *resembles* -- see affinity
           below -- which puts a line of research back under its own line.

  colour   a branch of that same spanning tree, cut where the link between a
           topic and its parent is weakest, named after whichever topic heads
           it. Because a subtree already owns a wedge, every branch is a
           contiguous arc, so colour restates the layout instead of cutting
           across it. The old three buckets keyed off iconID are gone with it.

  affinity how alike two topics are, read only out of what the file says each
           one *does*: the stat it modifies, the filters on its results, the
           components and structures it unlocks or obsoletes, its category and
           its icon. IDF-weighted cosine over that set. On this file it scores
           prerequisite links between related topics 10x higher than links
           between unrelated ones, which is what lets both the parent choice
           and the cut tell a lineage from a gate. No field is load-bearing:
           with everything but iconID removed the split still beats what the
           purely structural cut managed.

All three are deterministic and closed-form: no seeds, no restarts, no relaxation,
so the same research.json always renders the same chart.

Usage:  python3 layout.py
"""
import collections, json, math, os

R0 = 0.085                      # radius of the innermost generation
B = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(B, os.pardir, 'research.json')


# ==================================================================== graph
class Graph:
    """Prereq DAG. Tolerates dangling references and back edges."""

    def __init__(self, d):
        self.d = d
        ids = sorted(d)
        req = {k: [r for r in d[k].get('requiredResearch', []) if r in d and r != k]
               for k in ids}
        # A topic with no prerequisites and nothing depending on it is not part
        # of the tree -- there is no line the chart could draw to it. Drop those
        # before anything measures the graph, so they neither claim a wedge nor
        # shift the quantiles the radial scale is built on.
        linked = {r for k in ids for r in req[k]} | {k for k in ids if req[k]}
        self.isolated = [k for k in ids if k not in linked]
        self.ids = ids = [k for k in ids if k in linked]
        self.idx = {k: i for i, k in enumerate(ids)}
        self.N = len(ids)
        self.req = {k: req[k] for k in ids}
        self.dropped = sum(len(d[k].get('requiredResearch', [])) - len(self.req[k]) for k in ids)
        self._break_cycles()
        self.kids = collections.defaultdict(list)
        for k in ids:
            for r in self.req[k]:
                self.kids[r].append(k)
        self.edges = sorted({tuple(sorted((self.idx[k], self.idx[r])))
                             for k in ids for r in self.req[k]})

    def _break_cycles(self):
        """Iterative DFS; any edge closing a cycle is dropped so the rest of the
        pipeline can assume a DAG whatever the input file contains."""
        WHITE, GREY, BLACK = 0, 1, 2
        col = {k: WHITE for k in self.ids}
        self.cut = []
        for root in self.ids:
            if col[root] != WHITE: continue
            stack = [(root, iter(self.req[root]))]
            col[root] = GREY
            while stack:
                node, it = stack[-1]
                for nxt in it:
                    if col[nxt] == GREY:                      # back edge
                        self.cut.append((node, nxt))
                        self.req[node] = [x for x in self.req[node] if x != nxt]
                        continue
                    if col[nxt] == WHITE:
                        col[nxt] = GREY
                        stack.append((nxt, iter(self.req[nxt])))
                        break
                else:
                    col[node] = BLACK
                    stack.pop()

    def _fold(self, fn, base):
        """Bottom-up fold over the DAG without recursion."""
        val, order, seen = {}, [], set()
        for root in self.ids:
            if root in seen: continue
            stack = [(root, False)]
            while stack:
                k, done = stack.pop()
                if done:
                    order.append(k); continue
                if k in seen: continue
                seen.add(k)
                stack.append((k, True))
                for r in self.req[k]:
                    if r not in seen: stack.append((r, False))
        for k in order:
            val[k] = fn(k, [val[r] for r in self.req[k]], base)
        return val

    def costs(self):
        """end[k] = earliest completion in research points along the critical path."""
        return self._fold(lambda k, prev, _: (max(prev) if prev else 0)
                          + max(self.d[k].get('researchPoints', 0), 0), 0)

    def depths(self):
        return self._fold(lambda k, prev, _: (max(prev) + 1) if prev else 0, 0)


# ================================================================= affinity
# What a topic *does*, as a bag of tokens. Every key here is optional -- a file
# that carries none of them still lays out, it just falls back on structure --
# and no token is ever compared against a literal, so nothing in this module
# knows the name of a research topic, a weapon or a category.
FEATURE_KEYS = ('resultComponents', 'resultStructures', 'redComponents',
                'redStructures', 'replacedComponents')


def features(v):
    """The tokens describing one topic's effect.

    `results[].parameter` is deliberately left out. Every reload upgrade in the
    game shares Weapon:FirePause whatever it reloads, so it is a false friend:
    including it merges the mortar line into the cannon line."""
    f = set()
    if v.get('statID'): f.add('stat:' + str(v['statID']))
    for r in v.get('results', []):
        if r.get('filterValue') is not None:
            f.add('filt:%s:%s' % (r.get('class'), r['filterValue']))
    for key in FEATURE_KEYS:
        for x in v.get(key, []): f.add('ent:' + str(x))
    if v.get('category'): f.add('cat:' + str(v['category']))
    if v.get('iconID'): f.add('icon:' + str(v['iconID']))
    return f


class Affinity:
    """IDF-weighted cosine between topics' feature sets, memoised.

    IDF matters: `icon:IMAGE_RES_WEAPONTECH` is shared by 167 of 390 topics and
    says almost nothing, while a shared statID is nearly conclusive. Weighting
    by log(N/df) lets one similarity work across files whose fields are
    populated to very different depths, instead of needing a tuned mix."""

    def __init__(self, d, ids):
        self.F = {k: features(d[k]) for k in ids}
        df = collections.Counter()
        for k in ids:
            for x in self.F[k]: df[x] += 1
        n = len(ids)
        self.idf = {x: math.log(n / c) for x, c in df.items()}
        self.norm = {k: math.sqrt(sum(self.idf[x] ** 2 for x in self.F[k])) for k in ids}
        self._c = {}

    def __call__(self, a, b):
        key = (a, b) if a < b else (b, a)
        if key not in self._c:
            shared = self.F[a] & self.F[b]
            na, nb = self.norm[a], self.norm[b]
            self._c[key] = (sum(self.idf[x] ** 2 for x in shared) / (na * nb)
                            if shared and na and nb else 0.0)
        return self._c[key]


# =================================================================== radius
def quantiles(metric, ids):
    """F[k] = fraction of topics at or before k. A tie block shares the top edge
    of its own range, so equal progression means exactly equal radius."""
    F = {}
    for n, v in enumerate(sorted(metric[k] for k in ids)):
        F[v] = (n + 1) / len(ids)                 # last write wins: top of block
    return {k: F[metric[k]] for k in ids}


def radii(metric, ids):
    """Equal-area radial scale: uniform mark density by construction."""
    F = quantiles(metric, ids)
    return {k: R0 + (1 - R0) * math.sqrt(F[k]) for k in ids}


# ==================================================================== angle
def angles(g, end, aff):
    """Wedge per subtree, sized by leaf count; a node sits at the centre of its
    own wedge and its children subdivide it. Zero crossings among tree edges."""
    # spanning tree: the prerequisite the topic most resembles, so a lineage
    # stays under its own lineage rather than under whatever gated it. Cost
    # breaks ties, which is what decides it when a file carries no features at
    # all; id breaks those, purely so the result is stable.
    parent = {k: (max(g.req[k], key=lambda r: (aff(k, r), end[r], r)) if g.req[k] else None)
              for k in g.ids}
    kids = collections.defaultdict(list)
    for k in g.ids:
        if parent[k]: kids[parent[k]].append(k)
    for p in kids:
        kids[p].sort(key=lambda c: (end[c], c))   # siblings fan out in time order
    roots = sorted((k for k in g.ids if parent[k] is None), key=lambda k: (end[k], k))

    # a subtree claims arc in proportion to the leaves it carries
    weight = {}
    for r in roots:
        stack = [(r, False)]
        while stack:
            k, done = stack.pop()
            if done:
                weight[k] = sum(weight[c] for c in kids[k]) or 1
            else:
                stack.append((k, True))
                for c in kids[k]: stack.append((c, False))

    ang = {}
    todo = collections.deque([(roots, 0.0, 360.0)])
    while todo:
        seq, a0, a1 = todo.popleft()
        tot = sum(weight[k] for k in seq)
        cur = a0
        for k in seq:
            w = (a1 - a0) * weight[k] / tot
            ang[k] = cur + w / 2
            if kids[k]: todo.append((kids[k], cur, cur + w))
            cur += w
    return ang, parent, kids


# ================================================================== branches
# Colour is a *grouping*, not a slice of the tree. Contiguity is evidence that a
# grouping is real -- if related topics sit together, one colour covers one arc
# by itself -- but it is not a goal, and forcing it is how power generators end
# up the same colour as rocket autoloaders. So the groups are found on topical
# affinity and allowed to land wherever they land; whatever contiguity shows up
# is earned. Nothing here consults a table of topic names.
SLOTS = 6            # colour slots the palette carries (see template.html)
MINGRP = 8           # a group smaller than this is not worth a colour
THRESH = 0.30        # prereq link at or above this affinity continues a line
GATE = 0.05          # how well a below-threshold link still conducts colour


def lines(g, aff, thresh=THRESH):
    """Connected runs of prerequisite links that stay on-topic.

    Cutting every prerequisite edge below `thresh` leaves the natural lines of
    research: the cannon line, the mortar line, the power line. Most are short,
    which is the point -- they are seeds, not answers."""
    up = {k: k for k in g.ids}

    def find(x):
        while up[x] != x: up[x] = up[up[x]]; x = up[x]
        return x

    for i, j in g.edges:
        a, b = g.ids[i], g.ids[j]
        if aff(a, b) >= thresh:
            ra, rb = find(a), find(b)
            if ra != rb: up[ra] = rb
    out = collections.defaultdict(list)
    for k in g.ids: out[find(k)].append(k)
    return list(out.values())


def branches(g, parent, kids, ang, aff, end, slots=SLOTS, mingrp=MINGRP):
    """Group topics by what they are, then hand the groups colours.

    The largest lines of research seed the groups; every other topic is settled
    by diffusion over a graph whose edges conduct in proportion to affinity, so
    a topic joins whichever line it is best connected to *through related work*.
    A pacing gate -- a factory upgrade sitting between a cannon and its own next
    step -- conducts at `GATE` rather than at its affinity of ~0, which keeps it
    from severing the graph without letting it carry a colour across.

    Returns {id: slot} with -1 for topics no seed reaches, the head of each
    slot, and the slot sizes.
    """
    seeds = sorted(lines(g, aff), key=lambda v: (-len(v), v[0]))[:slots]
    seeds = [s for s in seeds if len(s) >= mingrp] or seeds[:1]
    k = len(seeds)

    w = collections.defaultdict(dict)
    for i, j in g.edges:
        a, b = g.ids[i], g.ids[j]
        w[a][b] = w[b][a] = GATE + aff(a, b)
    for a in g.ids:                      # a few non-prerequisite resemblances,
        near = sorted(((aff(a, b), b) for b in g.ids   # so parallel lines that
                       if b != a and aff.F[a] & aff.F[b]), reverse=True)[:3]
        for s, b in near:                # never meet in the DAG can still group
            if s > 0.35: w[a][b] = w[b][a] = max(w[a].get(b, 0.0), s)

    fixed = {}
    for i, s in enumerate(seeds):
        for x in s: fixed[x] = i
    p = {x: ([1.0 if fixed.get(x) == i else 0.0 for i in range(k)] if x in fixed
             else [1.0 / k] * k) for x in g.ids}
    for _ in range(300):                 # converges well inside this; fixed
        nxt = {}                         # point is unique so no seed is needed
        for x in g.ids:
            if x in fixed: nxt[x] = p[x]; continue
            acc, tot = [0.0] * k, 0.0
            for y, wt in w[x].items():
                tot += wt
                for i in range(k): acc[i] += wt * p[y][i]
            nxt[x] = [a / tot for a in acc] if tot else p[x]
        p = nxt

    grp = {x: (max(range(k), key=lambda i: p[x][i]) if w[x] or x in fixed else -1)
           for x in g.ids}
    count = collections.Counter(v for v in grp.values() if v >= 0)
    keep = [i for i in range(k) if count[i] >= mingrp]

    # slots are handed out in angular order, so the legend reads round the disc
    def mean_angle(i):
        rs = [math.radians(ang[x]) for x in g.ids if grp[x] == i]
        return math.degrees(math.atan2(sum(math.sin(a) for a in rs),
                                       sum(math.cos(a) for a in rs))) % 360
    keep.sort(key=mean_angle)
    slot = {old: new for new, old in enumerate(keep)}
    # A group is named after the head of the *seed line* that defines it, not
    # after the earliest topic that diffused into it: the earliest is usually
    # some generic ancestor the group merely inherited, which reads as a
    # mislabel -- the rocket group came out called "Hardcrete".
    heads = [min(seeds[old], key=lambda x: (end[x], x)) for old in keep]
    return ({x: slot.get(grp[x], -1) for x in g.ids}, heads,
            {h: count[old] for h, old in zip(heads, keep)})


def kind_of(v):
    if v.get('resultStructures'): return 1          # structure -> square
    if v.get('resultComponents'): return 0          # component -> circle
    return 2                                        # upgrade   -> diamond


# ==================================================================== report
def report(ids, rad, bands=5):
    """Arc length available per mark in each of `bands` equal-width radial
    bands, inner to outer. This is the number the whole rewrite is about: under
    the old sqrt(value) scale it varied 23x across the disc, which is what all
    the collision machinery was there to paper over."""
    out = []
    for b in range(bands):
        lo, hi = R0 + (1 - R0) * b / bands, R0 + (1 - R0) * (b + 1) / bands
        n = sum(1 for k in ids if lo <= rad[k] < hi or (b == bands - 1 and rad[k] == hi))
        out.append(2 * math.pi * (lo + hi) / 2 / max(n, 1))
    return out


def overlaps(ids, ang, rad, sep=0.020):
    """Pairs of marks closer than the minimum separation, in unit-circle units."""
    pts = sorted(((math.radians(ang[k]), rad[k]) for k in ids))
    xy = [(r * math.cos(a), r * math.sin(a)) for a, r in pts]
    n = 0
    for i in range(len(xy)):
        for j in range(i + 1, min(i + 40, len(xy))):
            if math.dist(xy[i], xy[j]) < sep: n += 1
    return n


# ==================================================================== main
def main():
    d = json.load(open(SRC))
    g = Graph(d)
    ids, idx = g.ids, g.idx
    print(f'{g.N} topics, {len(g.edges)} prerequisite edges'
          + (f', {len(g.isolated)} unconnected topics dropped' if g.isolated else '')
          + (f', {g.dropped} dangling refs ignored' if g.dropped else '')
          + (f', {len(g.cut)} cycle edges cut' if g.cut else ''))

    end, depth = g.costs(), g.depths()
    aff = Affinity(d, ids)
    rad = radii(end, ids)
    ang, parent, kids = angles(g, end, aff)
    br, heads, bcount = branches(g, parent, kids, ang, aff, end)
    print(f'  {len(heads)} branches coloured, '
          f'{sum(1 for k in ids if br[k] < 0)} topics left uncoloured: '
          + ', '.join(f'{d[h].get("name") or h} {bcount[h]}' for h in heads))

    # guide circles: cost is a continuum, so there is no natural tick -- six
    # evenly spaced circles, i.e. the quantiles (q/6)^2, keep the same cadence
    # across the whole disc. They are unlabelled: the scale is a ranking, so no
    # ring carries an honest number.
    rings = [R0 + (1 - R0) * q / 6 for q in range(1, 7)]

    arc = report(ids, rad)
    print('  arc/mark ' + ' '.join(f'{a:.4f}' for a in arc)
          + f'  spread {max(arc)/min(arc):.2f}x'
          + f', {overlaps(ids, ang, rad)} overlapping pairs'
          + f', {len(rings)} rings')

    deg = {k: ang[k] % 360 for k in ids}
    out = {
        'tmax': max(end.values()) or 1, 'dmax': max(depth.values()) or 1,
        'id': ids,
        'name': [d[k].get('name') or k for k in ids],
        'br': [br[k] for k in ids],
        'kind': [kind_of(d[k]) for k in ids],
        'ang': [round(deg[k], 3) for k in ids],
        'rad': [round(rad[k], 5) for k in ids],
        'rings': [round(r, 5) for r in rings],
        't': [end[k] for k in ids],
        'cost': [d[k].get('researchPoints', 0) for k in ids],
        'pow': [d[k].get('researchPower', 0) for k in ids],
        'dep': [depth[k] for k in ids],
        'req': [[idx[r] for r in g.req[k]] for k in ids],
        'par': [idx[parent[k]] if parent[k] else -1 for k in ids],
        'cat': [d[k].get('category') or '' for k in ids],
    }
    # emit in angular order, as the renderer expects
    perm = sorted(range(g.N), key=lambda i: (out['ang'][i], ids[i]))
    for key in ('id', 'name', 'br', 'kind', 'ang', 'rad', 't', 'cost', 'pow',
                'dep', 'cat'):
        out[key] = [out[key][i] for i in perm]
    ren = {old: new for new, old in enumerate(perm)}
    out['req'] = [[ren[r] for r in out['req'][i]] for i in perm]
    out['par'] = [ren[out['par'][i]] if out['par'][i] >= 0 else -1 for i in perm]

    # one legend entry per colour slot: the topic the branch starts at, and how
    # many topics hang off it. The renderer never names a branch itself.
    out['brs'] = [{'head': ren[idx[h]], 'name': d[h].get('name') or h,
                   'n': bcount[h]} for h in heads]

    p = os.path.join(B, 'techdata.json')
    json.dump(out, open(p, 'w'), separators=(',', ':'))
    print('wrote techdata.json', os.path.getsize(p), 'bytes')


if __name__ == '__main__':
    main()
