import json, math, collections, os

B = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(B, os.pardir, 'research.json')
d = json.load(open(SRC))

# ---------------------------------------------------------------- time
# "time" = earliest possible completion, in research points along the
# critical prerequisite path (each tech costs researchPoints).
end = {}
start = {}
def t_end(k):
    if k in end: return end[k]
    s = 0
    for r in d[k].get('requiredResearch', []):
        s = max(s, t_end(r))
    start[k] = s
    end[k] = s + d[k]['researchPoints']
    return end[k]
for k in d: t_end(k)

depth = {}
def dep(k):
    if k in depth: return depth[k]
    r = d[k].get('requiredResearch', [])
    depth[k] = 0 if not r else 1 + max(dep(x) for x in r)
    return depth[k]
for k in d: dep(k)

# ---------------------------------------------------------------- family
WPN = [('MG','mg'),('Flame','flamer'),('Flamer','flamer'),('Plasmite','flamer'),
       ('Cannon','cannon'),('Rocket','rocket'),('RocketSlow','rocket'),
       ('Missile','missile'),('HvArtMissile','missile'),('MdArtMissile','missile'),
       ('Mortar','mortar'),('Howitzer','howitzer'),
       ('Laser','laser'),('Energy','laser'),('EMP','laser'),('Plasma','laser'),
       ('Particle','laser'),('LasSat','laser'),
       ('Rail','rail'),('Bomb','air'),('AA','air'),('Sunburst','air')]

FORT = {'R-Defense-HardcreteWall','R-Defense-HardcreteGate','R-Defense-TankTrap01'}

def base_family(k):
    if k.startswith('R-Wpn-'):
        s = k[6:]
        best = None
        for pat, f in WPN:
            if s.startswith(pat) and (best is None or len(pat) > best[0]):
                best = (len(pat), f)
        return best[1] if best else 'cannon'
    if k.startswith('R-Cyborg-'): return 'cyborg'
    if k.startswith('R-Sys-'): return 'systems'
    if k.startswith('R-Struc-') or k.startswith('R-Comp-') or k == 'R-SuperTransport': return 'base'
    if k.startswith('R-Vehicle-'):
        s = k[10:]
        if s.startswith('Body') or s.startswith('Prop'): return 'chassis'
        return 'plating'
    if k.startswith('R-Defense-'):
        if k in FORT or k.startswith('R-Defense-WallUpgrade'): return 'fort'
        return None  # resolved from ancestry
    return 'base'

fam = {k: base_family(k) for k in d}
# defenses inherit the family of the nearest weapon ancestor
for k in list(fam):
    if fam[k] is not None: continue
    seen, q = set(), list(d[k].get('requiredResearch', []))
    got = None
    while q:
        x = q.pop(0)
        if x in seen: continue
        seen.add(x)
        f = fam.get(x)
        if f and f != 'fort':
            got = f; break
        q.extend(d[x].get('requiredResearch', []))
    fam[k] = got or 'fort'

ORDER = ['systems','base','chassis','plating','cyborg','mg','flamer','cannon',
         'mortar','howitzer','rocket','missile','air','laser','rail','fort']
assert set(ORDER) == set(fam.values()), set(fam.values()) ^ set(ORDER)

# ---------------------------------------------------------------- domain (colour)
def domain(k):
    if k.startswith('R-Wpn-'): return 'weapon'
    if k.startswith('R-Defense-'): return 'defense'
    if k.startswith('R-Cyborg-'): return 'cyborg'
    if k.startswith('R-Vehicle-'): return 'unit'
    if k.startswith('R-Sys-') or k.startswith('R-Comp-'): return 'system'
    return 'base'
dom = {k: domain(k) for k in d}

# ---------------------------------------------------------------- spanning tree
# primary parent = the prerequisite that gates the tech (latest finishing),
# preferring one inside the same family so lineages stay in their wedge.
parent = {}
for k in d:
    reqs = d[k].get('requiredResearch', [])
    if not reqs:
        parent[k] = None; continue
    same = [r for r in reqs if fam[r] == fam[k]]
    pool = same or reqs
    parent[k] = max(pool, key=lambda r: (end[r], r))

children = collections.defaultdict(list)
for k, p in parent.items():
    if p: children[p].append(k)

# ---------------------------------------------------------------- angles
counts = collections.Counter(fam.values())
GAP = 0.30            # degrees of padding between wedges, scaled below
total = sum(counts.values())
pad = 3.4             # degrees per wedge boundary
free = 360 - pad * len(ORDER)

wedge = {}
cur = 0.0
for f in ORDER:
    span = free * counts[f] / total
    wedge[f] = (cur, cur + span)
    cur += span + pad

def order_family(f):
    """DFS order of the family's internal forest; roots sorted by the wedge
    position of their outside parent so cross-wedge links stay short."""
    members = [k for k in d if fam[k] == f]
    mset = set(members)
    roots = [k for k in members if parent[k] not in mset]
    def ext_key(k):
        p = parent[k]
        if p is None: return -1
        return ORDER.index(fam[p])
    roots.sort(key=lambda k: (ext_key(k), end[k], k))
    out = []
    def walk(k):
        out.append(k)
        kids = sorted([c for c in children[k] if c in mset], key=lambda c: (end[c], c))
        for c in kids: walk(c)
    for r in roots: walk(r)
    assert len(out) == len(members)
    return out

slot = {}
for f in ORDER:
    seq = order_family(f)
    a0, a1 = wedge[f]
    n = len(seq)
    for i, k in enumerate(seq):
        slot[k] = a0 + (i + 0.5) * (a1 - a0) / n

# barycentre sweeps: nudge each node toward its neighbours, re-rank inside wedge
for _ in range(6):
    target = {}
    for k in d:
        nb = list(d[k].get('requiredResearch', [])) + [c for c in children[k]]
        nb = [x for x in nb if fam[x] == fam[k]]
        if not nb:
            target[k] = slot[k]; continue
        c, s = 0.0, 0.0
        for x in nb + [k, k]:
            a = math.radians(slot[x]); c += math.cos(a); s += math.sin(a)
        target[k] = math.degrees(math.atan2(s, c)) % 360
    for f in ORDER:
        seq = [k for k in d if fam[k] == f]
        a0, a1 = wedge[f]
        mid = (a0 + a1) / 2
        def rel(k):
            v = (target[k] - mid + 180) % 360 - 180
            return v
        seq.sort(key=lambda k: (rel(k), end[k], k))
        n = len(seq)
        for i, k in enumerate(seq):
            slot[k] = a0 + (i + 0.5) * (a1 - a0) / n

# ---------------------------------------------------------------- radius
tmax = max(end.values())
R0, R1 = 0.085, 1.0
def radius(k, mode='cost'):
    if mode == 'cost':
        u = math.sqrt(end[k] / tmax)
    else:
        u = depth[k] / max(depth.values())
    return R0 + (R1 - R0) * u

# ---------------------------------------------------------------- de-collide
# radius is fixed by time, so crowding can only be relieved along the arc.
# both radius modes share one set of angles, so relax against both at once.
MODES = {'cost': 0.020, 'depth': 0.015}
RAD = {m: {k: radius(k, m) for k in d} for m in MODES}
for it in range(300):
    push = collections.defaultdict(float)
    seq = sorted(d, key=lambda k: slot[k])
    n = len(seq)
    hits = 0
    for m, mind in MODES.items():
        rad = RAD[m]
        for i in range(n):
            a = seq[i]
            for j in range(i + 1, min(i + 16, n)):
                b = seq[j]
                da = (slot[b] - slot[a] + 180) % 360 - 180
                dr = rad[a] - rad[b]
                mid = (rad[a] + rad[b]) / 2
                arc = math.radians(abs(da)) * mid
                if math.hypot(arc, dr) >= mind: continue
                hits += 1
                need = math.sqrt(max(mind**2 - dr * dr, 0))
                gap = math.degrees((need - arc) / mid) / 2
                sgn = 1 if da >= 0 else -1
                push[a] -= sgn * gap * 0.6
                push[b] += sgn * gap * 0.6
    if not hits: break
    for k, v in push.items():
        a0, a1 = wedge[fam[k]]
        slot[k] = min(a1 - 0.04, max(a0 + 0.04, slot[k] + max(-0.8, min(0.8, v))))
print('relax stopped after', it + 1, 'passes, remaining overlaps:', hits)

angle = slot

# ---------------------------------------------------------------- report
xy = {k: (radius(k) * math.cos(math.radians(angle[k] - 90)),
          radius(k) * math.sin(math.radians(angle[k] - 90))) for k in d}
mind = 9
pairs = sorted(d, key=lambda k: angle[k])
for i, a in enumerate(pairs):
    for b in pairs[i+1:]:
        if (angle[b] - angle[a]) > 12: break
        dd = math.dist(xy[a], xy[b])
        if dd < mind: mind, worst = dd, (a, b)
print('closest pair', round(mind, 4), worst, d[worst[0]]['name'], '/', d[worst[1]]['name'])

cross = 0
for k in d:
    for r in d[k].get('requiredResearch', []):
        if r != parent[k]:
            cross += 1
print('spine edges', sum(1 for v in parent.values() if v), 'cross edges', cross)

def kind_of(k):
    v = d[k]
    if v.get('resultStructures'): return 1          # structure  -> square
    if v.get('resultComponents'): return 0          # component  -> circle
    return 2                                        # upgrade    -> diamond

SUPER = {'weapon': 0, 'defense': 0, 'unit': 1, 'cyborg': 1, 'system': 2, 'base': 2}

if __name__ == '__main__':
    ids = sorted(d, key=lambda k: angle[k])
    idx = {k: i for i, k in enumerate(ids)}
    out = {
        'tmax': tmax,
        'dmax': max(depth.values()),
        'order': ORDER,
        'wedge': {f: [round(wedge[f][0], 3), round(wedge[f][1], 3)] for f in ORDER},
        'id': ids,
        'name': [d[k]['name'] for k in ids],
        'fam': [ORDER.index(fam[k]) for k in ids],
        'sup': [SUPER[dom[k]] for k in ids],
        'dom': [dom[k] for k in ids],
        'kind': [kind_of(k) for k in ids],
        'ang': [round(angle[k], 3) for k in ids],
        't': [end[k] for k in ids],
        'cost': [d[k]['researchPoints'] for k in ids],
        'pow': [d[k].get('researchPower', 0) for k in ids],
        'dep': [depth[k] for k in ids],
        'req': [[idx[r] for r in d[k].get('requiredResearch', [])] for k in ids],
        'par': [idx[parent[k]] if parent[k] else -1 for k in ids],
        'cat': [d[k].get('category') or '' for k in ids],
    }
    p = os.path.join(B, 'techdata.json')
    json.dump(out, open(p, 'w'), separators=(',', ':'))
    print('wrote techdata.json', os.path.getsize(p), 'bytes')
