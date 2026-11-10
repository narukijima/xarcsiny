"""Turn a frozen events document into readable notation: MusicXML and MIDI.

The events hold every note the synth played, including stereo doubles and octave layers. A score for people
collapses those, quantises each beat to the simplest grid that fits, and leaves out what notation cannot carry
(pitch curves, filter motion, mix). Those live in the equation; the sheet says so in its caption.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import math
import re
import struct

DIV = 10080  # MusicXML divisions per quarter: every grid below divides it exactly
GRIDS = [1, 2, 4, 3, 6, 8, 5, 7, 9, 12, 16]  # subdivisions of one beat, tried in this order
SHARP_SPELL = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0), ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]
FLAT_SPELL = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0), ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)]
FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6}
MODE_SHIFT = {"major": 0, "minor": -3, "mixolydian": -1, "phrygian": -4, "dorian": -2, "lydian": 1}
DRUM_LINE = [("kick|thump|bd|stomp|808k", "F", 4), ("snare|clap|rim|snap|slap|conga|bongo|kendang|perc|tom|roll|dhol|tabla|cajon", "C", 5), ("hat|shaker|tick|guiro|tamb|ride|cymbal|crash|bell|cowbell", "G", 5)]
NOT_NOTES = re.compile("riser|swell|shep|gate|noise|wash", re.I)
NICE = {F(1), F(3, 2), F(2), F(3), F(4), F(6)}  # note lengths in beats that merge cleanly across beat lines


def fifths_of(key):
    """'F# minor (drop: G minor)' -> fifths of the opening key signature; unknown or chromatic -> 0."""
    m = re.match(r"\s*([A-G])(?:-?(sharp|flat)|([#b]))?\s*(major|minor|mixolydian|phrygian|dorian|lydian)?", key or "", re.I)
    if not m or not m.group(4):
        return 0
    tonic = m.group(1).upper() + {"sharp": "#", "flat": "b"}.get((m.group(2) or "").lower(), m.group(3) or "")
    return_value = FIFTHS.get(tonic)
    if return_value is None:
        return 0
    v = return_value + MODE_SHIFT[m.group(4).lower()]
    return ((v + 6) % 12) - 6 if abs(v) > 6 else v


def family(inst):
    """Stem id -> the instrument a reader cares about: stereo pairs, octave layers and timbre variants share one staff."""
    s = inst
    if re.match(r"b?808", s):
        return "808"
    s = re.sub(r"(_[lrLR]|[LR]|_near|_far|_in|_out)$", "", s) if len(s) > 3 else s
    s = re.sub(r"_(hi|lo|hi\d|lo\d|oct|ss|saw|w|v|m|d|k\d|open|dark|slow|mute|echo|str|lead|mel|solo|fast|pad)$", "", s)
    s = re.sub(r"[_\d]+$", "", s)
    s = re.sub(r"(wob|lead|acid|zap|riff|tok)[a-z]*$", r"\1", s)
    words = {"ep": "E. Piano", "epiano": "E. Piano", "gtr": "Guitar", "vox": "Voice", "voxline": "Voice", "eh": "Voice", "sub": "Sub bass", "mel": "Melody", "plk": "Pluck",
             "dbl": "Double", "harm": "Harmony", "acc": "Accordion", "wob": "Wobble", "str": "Strings", "reese": "Reese bass", "s": "Metallophone", "bellw": "Bell", "stabfm": "Stab",
             "resp": "Response", "tdrum": "Talking drum", "bcar": "Car", "verse": "Verse lead", "logdrum": "Log drum", "kit": "Toms", "drums": "Toms", "pop": "Slap bass", "perc": "Percussion",
             "arp": "Arpeggio", "low": "Low voice", "slow": "Slow car", "tok": "Riff", "riff": "Riff"}
    if s.lower() in words:
        return words[s.lower()]
    return s[:1].upper() + s[1:].replace("_", " ")


def pick_grid(fracs):
    """Simplest subdivision of a beat that holds these onsets, with room for swing."""
    if not fracs:
        return 1
    for d in GRIDS:
        tol = 0.075 if d in (1, 2, 4) else 0.022
        if d in (8, 16):
            tol = 0.03
        if all(abs(float(x) * d - round(float(x) * d)) / d <= tol for x in fracs):
            return d
    return 8


@dataclass
class Part:
    key: str
    name: str
    notes: list  # (beat Fraction, dur Fraction, midi or drum line index)
    drum: bool = False
    clef: tuple = ("G", 2, 0)


def stream_notes(e, doc):
    """Notes hidden inside a computed stream: a plucked-string recursion has a period, a bytebeat line has its X."""
    info = (doc.get("streams") or {}).get(e.get("stream"))
    if not info:
        return None
    beat, dur = F(e["beat"]), F(e["dur_beats"])
    sr = doc.get("sample_rate", 48000)
    if info.get("period"):
        return [(beat, dur, round(69 + 12 * math.log2(sr / (info["period"] + 0.5) / 440)))]
    if not info.get("rest_expr"):
        return None
    clock = info["clock"]
    sps = F(clock["steps_per_sample"])
    frames_per_beat = F(sr * 60) / F(doc["tempo_map"][0]["bpm"])
    code = compile(info["rest_expr"], "x", "eval")
    notes, pos = [], F(0)
    while pos < dur:
        frame = F(e.get("src", 0)) + pos * frames_per_beat
        t = clock["page"] + int((frame * sps + clock["rotation"]) % clock["cycle"])
        x = eval(code, {"__builtins__": {}}, {"t": t})  # our own formula from the frozen record
        step = min(F(1, 4) - (beat + pos) % F(1, 4) or F(1, 4), dur - pos)
        if x >= 2:
            notes.append((beat + pos, step, round(64 + 12 * math.log2(x / 16))))
        pos += step
    return notes


def read_parts(doc):
    """Group events into parts: identical or plain-octave copies collapse, unpitched stems share a drum staff."""
    pitched, drums, order = {}, {}, doc.get("inst_order") or []
    for e in doc["events"]:
        beat = F(e["beat"])
        if beat < 0:
            continue
        if "midi" in e:
            pitched.setdefault(e["inst"], []).append((beat, F(e["dur_beats"]), int(e["midi"])))
            continue
        hidden = stream_notes(e, doc)
        if hidden is not None:
            pitched.setdefault(e["inst"], []).extend(hidden)
        else:
            drums.setdefault(e.get("drum") or e["inst"], []).append((beat, F(e["dur_beats"])))
    kept = []
    for inst in sorted(pitched, key=lambda k: order.index(k) if k in order else 999):
        notes = sorted(pitched[inst])
        twin = False
        for other, onotes in kept:
            if len(onotes) == len(notes) and all(a[0] == b[0] for a, b in zip(notes, onotes)):
                gap = {a[2] - b[2] for a, b in zip(notes, onotes)}
                if len(gap) == 1 and next(iter(gap)) % 12 == 0:
                    twin = True
                    break
        if not twin:
            kept.append((inst, notes))
    families = {}
    names = doc.get("inst_names") or {}     # reader-facing names the track's record gives its code-named stems
    for inst, notes in kept:
        families.setdefault(names.get(inst) or family(inst), []).extend(notes)
    parts = []
    for inst, notes in families.items():
        notes = sorted(set(notes))
        mean = sum(n[2] for n in notes) / len(notes)
        if mean >= 88:
            clef = ("G", 2, 1)
        elif mean >= 58:
            clef = ("G", 2, 0)
        elif mean >= 38:
            clef = ("F", 4, 0)
        else:
            clef = ("F", 4, -1)
        parts.append((mean, Part(inst, inst, notes, False, clef)))
    parts.sort(key=lambda p: -p[0])
    seen, out = {}, []
    for _, p in parts:
        seen[p.name] = seen.get(p.name, 0) + 1
        if seen[p.name] > 1:
            p.name = f"{p.name} {seen[p.name]}"
        out.append(p)
    drum_notes = []
    for inst, hits in drums.items():
        if NOT_NOTES.search(inst):
            continue
        for i, (rx, step, octave) in enumerate(DRUM_LINE):
            if re.search(rx, inst, re.I):
                drum_notes += [(b, d, i) for b, d in hits]
                break
    if drum_notes:
        out.append(Part("drums", "Drums", sorted(set((b, F(1, 4), i) for b, d, i in drum_notes)), True, ("percussion", 2, 0)))
    return out


def beat_slots(notes, n_beats, drum):
    """Per-beat grids and one note stream per part: [(start, end, chord tuple)], snapped; overlaps cut at the next onset."""
    by_beat = {}
    for b, d, m in notes:
        by_beat.setdefault(math.floor(b), []).append(b - math.floor(b))
    grids = {k: pick_grid(sorted(set(v))) for k, v in by_beat.items()}

    def snap(t):
        i = math.floor(t)
        g = grids.get(i, 4)
        s = F(i) + F(round((t - i) * g), g)
        return s

    chords = {}
    for b, d, m in notes:
        s = snap(b)
        e = s + F(1, grids.get(math.floor(s), 4)) if drum else b + d
        if not drum:
            i = math.floor(e)
            e = F(i) + F(round((e - i) * grids.get(i, 4)), grids.get(i, 4))
        if e <= s:
            e = s + F(1, grids.get(math.floor(s), 4))
        c = chords.setdefault(s, [s, set()])
        c[0] = max(c[0], e)
        c[1].add(m)
    starts = sorted(chords)
    stream = []
    for i, s in enumerate(starts):
        e = chords[s][0]
        if i + 1 < len(starts):
            e = min(e, starts[i + 1])
        stream.append((s, min(e, F(n_beats)), tuple(sorted(chords[s][1]))))
    return grids, [x for x in stream if x[1] > x[0]]


def base_note(beats, tuplet_d):
    """(type, dots, normal denominator) of a chunk in beats. Tuplet chunks count in the tuplet's own unit."""
    table = [(F(4), "whole"), (F(2), "half"), (F(1), "quarter"), (F(1, 2), "eighth"), (F(1, 4), "16th"), (F(1, 8), "32nd"), (F(1, 16), "64th")]
    if tuplet_d:
        normal = 2 ** math.floor(math.log2(tuplet_d))
        real = beats * F(tuplet_d, normal)  # the written length inside the tuplet
    else:
        normal, real = None, beats
    for val, name in table:
        if real == val:
            return name, 0, normal
        if real == val * F(3, 2):
            return name, 1, normal
    return None


def split_binary(start, dur):
    """Largest writable pieces of a binary-grid length, kept inside beats so the pulse stays visible."""
    out, t, left = [], start, dur
    while left > 0:
        for v in (F(4), F(3), F(2), F(3, 2), F(1), F(3, 4), F(1, 2), F(3, 8), F(1, 4), F(3, 16), F(1, 8), F(1, 16)):
            if v > left:
                continue
            if v >= 1:
                if t.denominator != 1:
                    continue
            else:
                if math.floor(t) != math.floor(t + v - F(1, 4096)):
                    continue
                unit = v / 3 if v.numerator == 3 else v
                if (t / unit).denominator != 1:
                    continue
            out.append((t, v))
            t += v
            left -= v
            break
        else:
            out.append((t, left))
            break
    return out


def measure_chunks(stream, grids, bar_start, bar_beats):
    """Chunks in one bar: (start, dur, chord or None, tie_start, tie_stop, tuplet_d)."""
    bar_end = bar_start + bar_beats
    atoms = []
    t = bar_start
    pieces = [x for x in stream if x[1] > bar_start and x[0] < bar_end]
    for s, e, ch in pieces:
        s2, e2 = max(s, bar_start), min(e, bar_end)
        if s2 > t:
            atoms.append((t, s2, None, False, False))
        atoms.append((s2, e2, ch, s < bar_start, e > bar_end))
        t = e2
    if t < bar_end:
        atoms.append((t, bar_end, None, False, False))
    chunks = []
    for s, e, ch, tin, tout in atoms:
        pos = s
        first = True
        while pos < e:
            b = math.floor(pos)
            g = grids.get(b, 4)
            non_binary = g in (3, 5, 6, 7, 9, 12)
            if non_binary and ch is None and not any(x[0] < b + 1 and x[1] > b for x in pieces):
                non_binary = False
            if non_binary:
                stop = min(e, F(b + 1))
                chunks.append((pos, stop - pos, ch, (tin if first else True) if ch else False, (stop < e or tout) if ch else False, g))
            else:
                stop = e
                nb = F(b + 1)
                while nb < e and grids.get(int(nb), 4) not in (3, 5, 6, 7, 9, 12):
                    nb += 1
                stop = min(e, nb) if grids.get(int(nb), 4) in (3, 5, 6, 7, 9, 12) and nb < e else e
                for i, (ps, pd) in enumerate(split_binary(pos, stop - pos)):
                    head = pos == ps
                    last = ps + pd >= stop
                    chunks.append((ps, pd, ch, ((tin if first else True) if head else True) if ch else False, ((stop < e or tout) if last else True) if ch else False, 0))
            pos = stop
            first = False
    return chunks


def pitch_xml(midi, fifths):
    spell = FLAT_SPELL if fifths < 0 else SHARP_SPELL
    step, alter = spell[midi % 12]
    octave = midi // 12 - 1
    a = f"<alter>{alter}</alter>" if alter else ""
    return f"<pitch><step>{step}</step>{a}<octave>{octave}</octave></pitch>"


def chunk_xml(c, part, fifths, tup_state, beam="", voice=1):
    start, dur, chord, tin, tout, tup = c
    ticks = int(dur * DIV)
    desc = base_note(dur, tup) if tup else base_note(dur, 0)
    tup_xml, tup_note = "", ""
    if tup:
        normal = 2 ** math.floor(math.log2(tup))
        if not desc or dur * tup != int(dur * tup):
            desc = ("16th", 0, normal)
        tup_xml = f"<time-modification><actual-notes>{tup}</actual-notes><normal-notes>{normal}</normal-notes></time-modification>"
    if not desc:
        desc = ("16th", 0, None)
    name, dots, _ = desc
    dot_xml = "<dot/>" * dots
    out = []
    if tup and tup_state.get("beat") != math.floor(start):
        tup_state["beat"] = math.floor(start)
        tup_note = '<tuplet type="start" bracket="no"/>'
    if tup and start + dur >= math.floor(start) + 1:
        tup_note += '<tuplet type="stop"/>'
        tup_state["beat"] = None
    notation = tup_note
    ties = ""
    if tin:
        ties += '<tie type="stop"/>'
        notation += '<tied type="stop"/>'
    if tout:
        ties += '<tie type="start"/>'
        notation += '<tied type="start"/>'
    notation = f"<notations>{notation}</notations>" if notation else ""
    if chord is None:
        return f'<note><rest/><duration>{ticks}</duration><voice>{voice}</voice><type>{name}</type>{dot_xml}{tup_xml}{notation}</note>'
    for i, m in enumerate(chord):
        c_tag = "<chord/>" if i else ""
        if part.drum:
            step, line = DRUM_LINE[m][1], DRUM_LINE[m][2]
            head = "<notehead>x</notehead>" if m == 2 else ""
            body = f"<unpitched><display-step>{step}</display-step><display-octave>{line}</display-octave></unpitched>"
            out.append(f'<note>{c_tag}{body}<duration>{ticks}</duration><voice>{voice}</voice><type>{name}</type>{dot_xml}{tup_xml}{head}{beam if not i else ""}{notation}</note>')
        else:
            out.append(f'<note>{c_tag}{pitch_xml(m, fifths)}<duration>{ticks}</duration>{ties}<voice>{voice}</voice><type>{name}</type>{dot_xml}{tup_xml}{beam if not i else ""}{notation}</note>')
    return "".join(out)


def tempo_marks(doc, bar_beats):
    """(bar index, bpm) wherever the rounded tempo moves. Long ramps show their milestones, not every step."""
    marks, last = [], None
    for tm in doc["tempo_map"]:
        beat, bpm = F(tm["beat"]), float(F(tm["bpm"]))
        if beat < 0:
            continue
        rnd = round(bpm)
        if last is None or abs(rnd - last) >= 2:
            bar = int(beat // bar_beats)
            if marks and marks[-1][0] == bar:
                marks[-1] = (bar, rnd)
            else:
                marks.append((bar, rnd))
            last = rnd
    if not marks:
        marks = [(0, round(float(F(doc["tempo_map"][0]["bpm"]))))]
    return marks


def meter_of(track, doc):
    bb = int(doc.get("beats_per_bar") or 4)
    m = re.match(r"(\d+)/(\d+)", track.get("meter") or "")
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        if F(n * 4, d) == bb:
            return n, d, bb
    return bb, 4, bb


def beams_for(chunks, unit):
    """One primary beam per beat group; rests and notes of a quarter or longer break it."""
    tags = [""] * len(chunks)
    group, key = [], None

    def flush():
        if len(group) > 1:
            for k, j in enumerate(group):
                kind = "begin" if k == 0 else ("end" if k == len(group) - 1 else "continue")
                tags[j] = f'<beam number="1">{kind}</beam>'
        group.clear()

    for j, c in enumerate(chunks):
        start, dur, chord, *_ , tup = c
        g = math.floor(start / unit)
        if chord is None or (dur >= 1 and not tup):
            flush()
            key = None
            continue
        if g != key:
            flush()
            key = g
        group.append(j)
    flush()
    return tags


class Score:
    """Parts and bar geometry of one track, ready to write whole or one line at a time."""

    def __init__(self, doc, track, title, composer="x=arcsin y"):
        self.doc, self.title, self.composer = doc, title, composer
        self.n, self.d, self.bar_beats = meter_of(track, doc)
        self.parts = read_parts(doc)
        last = max((b + dur for p in self.parts for b, dur, _ in p.notes), default=F(4))
        self.n_bars = int(math.ceil(last / self.bar_beats))
        self.fifths = fifths_of(track.get("key") or doc.get("key"))
        self.marks = dict(tempo_marks(doc, self.bar_beats))
        self.sections = {s["bar"]: s["name"] for s in doc.get("sections") or []}
        self.unit = F(3, 2) if self.d == 8 and self.n % 3 == 0 else F(1)
        n_beats = self.n_bars * self.bar_beats
        self.slots = [beat_slots(p.notes, n_beats, p.drum) for p in self.parts]

    def busy_parts(self, first, last):
        lo, hi = first * self.bar_beats, last * self.bar_beats
        return [i for i, p in enumerate(self.parts) if any(lo <= b < hi for b, _, _ in p.notes)]

    def density(self, bar):
        lo, hi = bar * self.bar_beats, (bar + 1) * self.bar_beats
        return max((sum(1 for b, _, _ in p.notes if lo <= b < hi) for p in self.parts), default=0)

    def xml(self, first=0, last=None, part_ids=None, head_marks=True):
        last = self.n_bars if last is None else last
        ids = list(range(len(self.parts))) if part_ids is None else part_ids
        head = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
                '<score-partwise version="4.0">', f"<work><work-title>{esc(self.title)}</work-title></work>",
                f'<identification><creator type="composer">{esc(self.composer)}</creator></identification>', "<part-list>"]
        for i in ids:
            head.append(f'<score-part id="P{i+1}"><part-name>{esc(self.parts[i].name)}</part-name></score-part>')
        head.append("</part-list>")
        body = []
        for pos, i in enumerate(ids):
            p = self.parts[i]
            grids, stream = self.slots[i]
            body.append(f'<part id="P{i+1}">')
            tup = {}
            for bar in range(first, last):
                bs = F(bar * self.bar_beats)
                x = [f'<measure number="{bar+1}">']
                if bar == first:
                    clef = '<clef><sign>percussion</sign><line>2</line></clef>' if p.drum else (
                        f"<clef><sign>{p.clef[0]}</sign><line>{p.clef[1]}</line>" + (f"<clef-octave-change>{p.clef[2]}</clef-octave-change>" if p.clef[2] else "") + "</clef>")
                    show_time = "" if first == 0 or not head_marks else ' print-object="no"'
                    x.append(f"<attributes><divisions>{DIV}</divisions><key><fifths>{0 if p.drum else self.fifths}</fifths></key>"
                             f'<time{show_time}><beats>{self.n}</beats><beat-type>{self.d}</beat-type></time>{clef}</attributes>')
                if pos == 0 and bar in self.marks:
                    x.append(f'<direction placement="above"><direction-type><words>{self.marks[bar]} BPM</words></direction-type><sound tempo="{self.marks[bar]}"/></direction>')
                if pos == 0 and not head_marks and bar in self.sections and bar:
                    x.append(f'<direction placement="above"><direction-type><rehearsal>{esc(self.sections[bar])}</rehearsal></direction-type></direction>')
                chunks = measure_chunks(stream, grids, bs, self.bar_beats)
                if all(c[2] is None for c in chunks):
                    x.append(f'<note><rest measure="yes"/><duration>{int(self.bar_beats*DIV)}</duration><voice>1</voice></note>')
                else:
                    tags = beams_for(chunks, self.unit)
                    for c, tag in zip(chunks, tags):
                        x.append(chunk_xml(c, p, self.fifths, tup, tag))
                x.append("</measure>")
                body.append("".join(x))
            body.append("</part>")
        return "\n".join(head + body + ["</score-partwise>"])


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vlq(v):
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    return bytes(reversed(out))


def to_midi(doc, parts, title):
    """Standard MIDI file, format 1: one track per score part, the exact (unquantised) beats, tempo map on track 0."""
    tpq = 960

    def tick(b):
        return int(round(b * tpq))

    def chunk(data):
        return b"MTrk" + struct.pack(">I", len(data)) + data

    meta = [(0, b"\xff\x03" + vlq(len(title.encode())) + title.encode())]
    for tm in doc["tempo_map"]:
        b = F(tm["beat"])
        if b < 0:
            continue
        us = int(round(60_000_000 / float(F(tm["bpm"]))))
        meta.append((tick(b), b"\xff\x51\x03" + us.to_bytes(3, "big")))
    tracks = []
    data, last = b"", 0
    for t, m in sorted(meta, key=lambda x: x[0]):
        data += vlq(t - last) + m
        last = t
    tracks.append(chunk(data + b"\x00\xff\x2f\x00"))
    drum_keys = [36, 38, 42]
    for i, p in enumerate(parts):
        ch = 9 if p.drum else min(i if i < 9 else i + 1, 15)
        ev = []
        for b, d, m in p.notes:
            key = drum_keys[m] if p.drum else m
            if not 0 <= key <= 127:
                continue
            ev.append((tick(b), 1, key))
            ev.append((tick(b + d), 0, key))
        ev.sort(key=lambda e: (e[0], e[1]))
        name = p.name.encode()
        data, last = b"\x00\xff\x03" + vlq(len(name)) + name, 0
        for t, on, key in ev:
            data += vlq(t - last) + bytes([(0x90 if on else 0x80) | ch, key, 96 if on else 0])
            last = t
        tracks.append(chunk(data + b"\x00\xff\x2f\x00"))
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), tpq) + b"".join(tracks)
