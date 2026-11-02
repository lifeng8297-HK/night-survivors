"""Game rules for Night Survivors.

Pure Python: no pygame here. The game advances in fixed steps of 1/60 s.
Every number comes from data/game.json (which copies the numbers from GAME.md).
Every word comes from data/text.json, in the language game.json asks for.
"""
import json
import math
import os
import random

STEP = 1.0 / 60.0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_data():
    with open(os.path.join(BASE_DIR, "data", "game.json"), encoding="utf-8") as f:
        return json.load(f)


def load_text():
    with open(os.path.join(BASE_DIR, "data", "text.json"), encoding="utf-8") as f:
        return json.load(f)


def dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


class Enemy:
    def __init__(self, kind, spec, x, y):
        self.kind = kind
        self.x = x
        self.y = y
        self.hp = spec["hp"]
        self.max_hp = spec["hp"]
        self.speed = spec["speed"]
        self.damage = spec["damage"]
        self.xp = spec["xp"]
        self.radius = spec["radius"]
        self.is_boss = spec.get("boss", False)
        self.touch_cd = 0.0      # time until it can hurt the hero again
        self.blade_cd = 0.0      # time until the blades can hit it again
        self.dead = False

    def take_damage(self, amount):
        self.hp -= amount


class Gem:
    def __init__(self, x, y, value):
        self.x = x
        self.y = y
        self.value = value


class Spark:
    def __init__(self, x, y, vx, vy, damage):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.dead = False


class Weapon:
    def __init__(self, kind):
        self.kind = kind
        self.level = 1
        self.timer = 0.0     # time until the next attack
        self.angle = 0.0     # for Spin Blades


class Game:
    """One run of the game. States: "playing", "levelup", "won", "lost"."""

    def __init__(self, data=None, seed=None, text=None, lang=None):
        self.data = data if data is not None else load_data()
        self.step = self.data["fixed_dt"]      # the size of one step comes from the data
        self.rng = random.Random(seed)
        self.text_all = text if text is not None else load_text()
        self.set_language(lang or self.data.get("language", "en"))
        self.reset()

    def set_language(self, lang):
        """Switch the words on the screen; the numbers stay the same."""
        if lang not in self.text_all:
            return False
        self.lang = lang
        self.T = self.text_all[lang]
        return True

    def name_of(self, kind):
        return self.T["names"][kind]

    def line_of(self, key, **values):
        return self.T["lines"][key].format(**values)

    def reset(self):
        hero = self.data["hero"]
        self.state = "playing"
        self.time = 0.0
        self.kills = 0
        self.level = 1
        self.xp = 0
        self.hero_x = 0.0
        self.hero_y = 0.0
        self.hero_hp = hero["hp"]
        self.hero_max_hp = hero["hp"]
        self.move_target = None          # (x, y) in world coords, or None
        self.enemies = []
        self.gems = []
        self.sparks = []
        self.weapons = [Weapon("spark")]
        self.passives = {}               # kind -> level
        self.spawn_timer = 0.0           # 0 -> bats appear on the very first step
        self.boss_spawned = False
        self.cards = []
        self.events = []                 # what happened this step (sounds, popups)
        self.paused = False              # P pause (main.py sets this)

    # -- helper numbers -------------------------------------------------

    def xp_needed(self, level):
        xp = self.data["xp"]
        return xp["base"] + xp["per_level"] * (level - 1)

    def weapon_level(self, kind):
        for w in self.weapons:
            if w.kind == kind:
                return w.level
        return 0

    def passive_level(self, kind):
        return self.passives.get(kind, 0)

    def hero_speed(self):
        boots = self.data["passives"]["boots"]
        bonus = self.passive_level("boots") * boots["speed_bonus_percent"]
        return self.data["hero"]["speed"] * (1 + bonus / 100.0)

    def hero_magnet_radius(self):
        magnet = self.data["passives"]["magnet"]
        return self.data["hero"]["magnet_radius"] + self.passive_level("magnet") * magnet["magnet_bonus"]

    def current_wave(self):
        wave = self.data["waves"][0]
        for w in self.data["waves"]:
            if self.time >= w["from"]:
                wave = w
        return wave

    def spark_count(self, w):
        spec = self.data["weapons"]["spark"]
        n = 1
        for lvl in spec["extra_spark_levels"]:
            if w.level >= lvl:
                n += 1
        return n

    def spark_interval(self, w):
        spec = self.data["weapons"]["spark"]
        return max(0.05, spec["interval"] - spec["interval_per_level"] * (w.level - 1))

    def spark_damage(self, w):
        spec = self.data["weapons"]["spark"]
        return spec["damage"] + spec["damage_per_level"] * (w.level - 1)

    def blade_count(self, w):
        spec = self.data["weapons"]["blades"]
        n = spec["count"]
        for lvl in spec["extra_blade_levels"]:
            if w.level >= lvl:
                n += 1
        return n

    def blade_damage(self, w):
        spec = self.data["weapons"]["blades"]
        return spec["damage"] + spec["damage_per_level"] * (w.level - 1)

    def ring_damage(self, w):
        spec = self.data["weapons"]["ring"]
        return spec["damage"] + spec["damage_per_level"] * (w.level - 1)

    def ring_radius(self, w):
        spec = self.data["weapons"]["ring"]
        return spec["radius"] + spec["radius_per_level"] * (w.level - 1)

    # -- level-up cards --------------------------------------------------

    def card_options(self):
        """Everything the player may be offered: a new weapon, a weapon level,
        or a passive item. Never something already at level 5."""
        opts = []
        if len(self.weapons) < self.data["levelup"]["max_weapons"]:
            for kind in self.data["weapons"]:
                if self.weapon_level(kind) == 0:
                    opts.append(("new_weapon", kind))
        for w in self.weapons:
            if w.level < self.data["weapons"][w.kind]["max_level"]:
                opts.append(("upgrade_weapon", w.kind))
        for kind in self.data["passives"]:
            if self.passive_level(kind) < self.data["passives"][kind]["max_level"]:
                opts.append(("passive", kind))
        if not opts:
            opts.append(("heal", None))
        return opts

    def card_text(self, card):
        """(name, level line, one line of what it does) for the screen."""
        kind, name = card
        lvl_txt = self.T["level"].format(n=1)
        if kind == "new_weapon":
            return (self.name_of(name), lvl_txt, self._weapon_line(name, 1))
        if kind == "upgrade_weapon":
            lvl = self.weapon_level(name) + 1
            return (self.name_of(name), self.T["level"].format(n=lvl), self._weapon_line(name, lvl))
        if kind == "passive":
            lvl = self.passive_level(name) + 1
            return (self.name_of(name), self.T["level"].format(n=lvl), self._passive_line(name))
        return (self.T["heal_name"], "", self.line_of("heal", hp=self.data["levelup"]["heal"]))

    def _weapon_line(self, kind, lvl):
        spec = self.data["weapons"][kind]
        dmg = spec["damage"] + spec["damage_per_level"] * (lvl - 1)
        if kind == "spark":
            rate = max(0.05, spec["interval"] - spec["interval_per_level"] * (lvl - 1))
            return self.line_of("spark", dmg=dmg, rate="%.2f" % rate)
        if kind == "blades":
            n = spec["count"] + sum(1 for x in spec["extra_blade_levels"] if lvl >= x)
            return self.line_of("blades", n=n, dmg=dmg)
        if kind == "ring":
            rad = spec["radius"] + spec["radius_per_level"] * (lvl - 1)
            return self.line_of("ring", dmg=dmg, rad=rad)
        return ""

    def _passive_line(self, kind):
        spec = self.data["passives"][kind]
        if kind == "boots":
            return self.line_of("boots", pct=spec["speed_bonus_percent"])
        if kind == "heart":
            return self.line_of("heart", hp=spec["max_hp_bonus"], heal=spec["heal"])
        if kind == "magnet":
            return self.line_of("magnet", px=spec["magnet_bonus"])
        return ""

    def make_cards(self):
        opts = self.card_options()
        n = min(self.data["levelup"]["cards"], len(opts))
        self.cards = self.rng.sample(opts, n)

    def choose_card(self, index):
        if self.state != "levelup" or not (0 <= index < len(self.cards)):
            return
        kind, name = self.cards[index]
        if kind == "new_weapon":
            self.weapons.append(Weapon(name))
        elif kind == "upgrade_weapon":
            for w in self.weapons:
                if w.kind == name:
                    w.level += 1
        elif kind == "passive":
            self.passives[name] = self.passive_level(name) + 1
            if name == "heart":
                spec = self.data["passives"]["heart"]
                self.hero_max_hp += spec["max_hp_bonus"]
                self.hero_hp = min(self.hero_max_hp, self.hero_hp + spec["heal"])
        elif kind == "heal":
            self.hero_hp = min(self.hero_max_hp, self.hero_hp + self.data["levelup"]["heal"])
        self.cards = []
        self.state = "playing"

    # -- main update ------------------------------------------------------

    def update(self, dt=None):
        if dt is None:
            dt = self.step
        self.events = []
        if self.state != "playing" or self.paused:
            return
        self.time += dt
        if self.time >= self.data["win_time"]:
            self.state = "won"
            self.events.append(("win",))
            return
        self._move_hero(dt)
        self._spawn(dt)
        self._update_enemies(dt)
        self._update_weapons(dt)
        self._update_sparks(dt)
        self._update_gems(dt)
        self.enemies = [e for e in self.enemies if not e.dead]
        self._check_levelup()
        if self.hero_hp <= 0 and self.state == "playing":
            self.hero_hp = 0
            self.state = "lost"
            self.events.append(("lose",))

    def _move_hero(self, dt):
        if self.move_target is None:
            return
        tx, ty = self.move_target
        d = dist(self.hero_x, self.hero_y, tx, ty)
        if d <= self.data["hero"]["stop_distance"]:
            return
        step = min(self.hero_speed() * dt, d)
        self.hero_x += (tx - self.hero_x) / d * step
        self.hero_y += (ty - self.hero_y) / d * step

    def _spawn(self, dt):
        sp = self.data["spawning"]
        self.spawn_timer -= dt
        if self.spawn_timer > 0:
            return
        self.spawn_timer = sp["check_interval"]
        wave = self.current_wave()
        if wave.get("boss") and not self.boss_spawned:
            self.boss_spawned = True
            self._spawn_one("demon")
        need = wave["min_alive"] - len(self.enemies)
        for _ in range(min(need, sp["max_per_second"])):
            if len(self.enemies) >= sp["max_alive"]:
                break
            self._spawn_one(self.rng.choice(wave["types"]))

    def _spawn_one(self, kind):
        sp = self.data["spawning"]
        a = self.rng.uniform(0, math.tau)
        x = self.hero_x + math.cos(a) * sp["circle_radius"]
        y = self.hero_y + math.sin(a) * sp["circle_radius"]
        self.enemies.append(Enemy(kind, self.data["enemies"][kind], x, y))

    def _update_enemies(self, dt):
        sp = self.data["spawning"]
        hero_r = self.data["hero"]["hit_radius"]
        for e in self.enemies:
            if e.dead:
                continue
            # walk toward the hero
            dd = dist(e.x, e.y, self.hero_x, self.hero_y)
            if dd > 0:
                step = min(e.speed * dt, dd)
                e.x += (self.hero_x - e.x) / dd * step
                e.y += (self.hero_y - e.y) / dd * step
            # touching the hero hurts him, at most once per cooldown
            e.touch_cd -= dt
            if e.touch_cd <= 0 and dist(e.x, e.y, self.hero_x, self.hero_y) <= e.radius + hero_r:
                self.hero_hp -= e.damage
                e.touch_cd = self.data["contact_damage_cooldown"]
                self.events.append(("hurt", e.damage))
        # the map is endless: normal enemies left far behind are removed,
        # the boss is only moved back so it keeps following you
        alive = []
        for e in self.enemies:
            if e.dead:
                continue
            dd = dist(e.x, e.y, self.hero_x, self.hero_y)
            if e.is_boss:
                if dd > sp["boss_reset_distance"]:
                    a = self.rng.uniform(0, math.tau)
                    e.x = self.hero_x + math.cos(a) * sp["circle_radius"]
                    e.y = self.hero_y + math.sin(a) * sp["circle_radius"]
                alive.append(e)
            elif dd <= sp["remove_distance"]:
                alive.append(e)
        self.enemies = alive

    def _update_weapons(self, dt):
        for w in self.weapons:
            if w.kind == "spark":
                self._update_spark_wand(w, dt)
            elif w.kind == "blades":
                self._update_blades(w, dt)
            elif w.kind == "ring":
                self._update_ring(w, dt)

    def _update_spark_wand(self, w, dt):
        spec = self.data["weapons"]["spark"]
        w.timer -= dt
        if w.timer > 0 or not self.enemies:
            return
        w.timer = self.spark_interval(w)
        n = self.spark_count(w)
        targets = sorted(self.enemies, key=lambda e: dist(e.x, e.y, self.hero_x, self.hero_y))
        for i in range(n):
            e = targets[i % len(targets)]
            dd = dist(self.hero_x, self.hero_y, e.x, e.y)
            if dd == 0:
                # an enemy sits exactly on the hero: any direction still hits it
                a = self.rng.uniform(0, math.tau)
                vx = math.cos(a) * spec["spark_speed"]
                vy = math.sin(a) * spec["spark_speed"]
            else:
                vx = (e.x - self.hero_x) / dd * spec["spark_speed"]
                vy = (e.y - self.hero_y) / dd * spec["spark_speed"]
            self.sparks.append(Spark(self.hero_x, self.hero_y, vx, vy, self.spark_damage(w)))
        self.events.append(("shoot",))

    def _update_blades(self, w, dt):
        spec = self.data["weapons"]["blades"]
        w.angle += math.tau * dt / spec["turn_time"]
        n = self.blade_count(w)
        for e in self.enemies:
            e.blade_cd -= dt
            if e.blade_cd > 0:
                continue
            for i in range(n):
                a = w.angle + math.tau * i / n
                bx = self.hero_x + math.cos(a) * spec["orbit_radius"]
                by = self.hero_y + math.sin(a) * spec["orbit_radius"]
                if dist(e.x, e.y, bx, by) <= e.radius + spec["blade_radius"]:
                    self._damage_enemy(e, self.blade_damage(w))
                    e.blade_cd = spec["hit_cooldown"]
                    break

    def _update_ring(self, w, dt):
        w.timer -= dt
        if w.timer > 0:
            return
        w.timer = self.data["weapons"]["ring"]["interval"]
        r = self.ring_radius(w)
        for e in self.enemies:
            if not e.dead and dist(e.x, e.y, self.hero_x, self.hero_y) <= r + e.radius:
                self._damage_enemy(e, self.ring_damage(w))

    def _damage_enemy(self, e, amount):
        if e.dead:
            return
        e.take_damage(amount)
        self.events.append(("hit", e.x, e.y, amount))
        if e.hp <= 0:
            e.dead = True
            self.kills += 1
            if e.xp > 0:
                self.gems.append(Gem(e.x, e.y, e.xp))
            self.events.append(("enemy_die", e.x, e.y))

    def _update_sparks(self, dt):
        spec = self.data["weapons"]["spark"]
        for s in self.sparks:
            if s.dead:
                continue
            s.x += s.vx * dt
            s.y += s.vy * dt
            if dist(s.x, s.y, self.hero_x, self.hero_y) > spec["spark_range"]:
                s.dead = True
                continue
            for e in self.enemies:
                if not e.dead and dist(s.x, s.y, e.x, e.y) <= e.radius + spec["spark_radius"]:
                    self._damage_enemy(e, s.damage)
                    s.dead = True
                    break
        self.sparks = [s for s in self.sparks if not s.dead]

    def _update_gems(self, dt):
        hero_r = self.data["hero"]["hit_radius"]
        magnet = self.hero_magnet_radius()
        speed = self.data["xp"]["gem_speed"]
        keep = []
        for g in self.gems:
            dd = dist(g.x, g.y, self.hero_x, self.hero_y)
            if dd <= hero_r:
                self.xp += g.value
                self.events.append(("gem", g.value))
                continue
            if dd <= magnet:
                step = min(speed * dt, dd)
                g.x += (self.hero_x - g.x) / dd * step
                g.y += (self.hero_y - g.y) / dd * step
            keep.append(g)
        self.gems = keep

    def _check_levelup(self):
        while self.xp >= self.xp_needed(self.level) and self.state == "playing":
            self.xp -= self.xp_needed(self.level)
            self.level += 1
            self.state = "levelup"
            self.make_cards()
            self.events.append(("levelup",))
