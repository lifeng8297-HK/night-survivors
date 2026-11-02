"""Tests for the rules in rules.py. No pygame, no drawing, no sounds.

Every expected number is read from data/game.json, so the tests follow GAME.md.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules import STEP, Game, load_data  # noqa: E402


def run(game, seconds):
    """Advance the game by N seconds in fixed steps."""
    for _ in range(int(seconds / STEP)):
        game.update(STEP)


class TestBase(unittest.TestCase):
    def setUp(self):
        self.data = load_data()
        self.game = Game(self.data, seed=1)

    def no_weapons(self):
        self.game.weapons.clear()

    def no_spawns(self):
        self.game.spawn_timer = 10**9

    def frozen_enemy(self, kind, x=None, y=None):
        """An enemy that stands still where we put it."""
        self.game._spawn_one(kind)
        e = self.game.enemies[-1]
        e.speed = 0
        e.x = self.game.hero_x + (60 if x is None else x)
        e.y = self.game.hero_y + (0 if y is None else y)
        return e


class TestCore(TestBase):
    def test_the_step_size_comes_from_the_data(self):
        """Changing fixed_dt in data/game.json must change the simulation."""
        game = Game(dict(self.data, fixed_dt=0.05), seed=1)
        game.update()
        self.assertAlmostEqual(game.time, 0.05)
        self.assertEqual(game.step, 0.05)

    def test_the_weapon_cap_comes_from_the_data(self):
        from rules import Weapon
        self.game.weapons = [Weapon("spark")]
        for cap, expected in ((1, 0), (3, len(self.data["weapons"]) - 1)):
            data = dict(self.data)
            data["levelup"] = dict(self.data["levelup"], max_weapons=cap)
            self.game.data = data
            kinds = [c for c in self.game.card_options() if c[0] == "new_weapon"]
            self.assertEqual(len(kinds), expected, cap)

    def test_hero_walks_to_the_pointer(self):
        self.no_weapons()
        self.no_spawns()
        self.game.move_target = (300.0, 0.0)
        run(self.game, 1.0)
        self.assertAlmostEqual(self.game.hero_x, self.data["hero"]["speed"], delta=1.0)
        # he keeps walking while the pointer stays still, and stops at stop_distance
        run(self.game, 3.0)
        stop = self.data["hero"]["stop_distance"]
        self.assertAlmostEqual(abs(300 - self.game.hero_x), stop, delta=1.0)

    def test_spawning(self):
        self.no_weapons()
        self.game.update(STEP)  # the first spawn happens on the very first step
        sp = self.data["spawning"]
        self.assertLessEqual(len(self.game.enemies), sp["max_per_second"])
        self.assertTrue(all(e.kind == "bat" for e in self.game.enemies))
        for e in self.game.enemies:
            d = ((e.x - self.game.hero_x) ** 2 + (e.y - self.game.hero_y) ** 2) ** 0.5
            self.assertAlmostEqual(d, sp["circle_radius"], delta=3.0)
        run(self.game, 3.0)
        self.assertEqual(len(self.game.enemies), self.data["waves"][0]["min_alive"])

    def test_enemies_far_behind_are_removed(self):
        self.no_weapons()
        self.no_spawns()
        e = self.frozen_enemy("bat", self.data["spawning"]["remove_distance"] + 200)
        self.game.update(STEP)
        self.assertNotIn(e, self.game.enemies)

    def test_contact_damage_once_per_cooldown(self):
        self.no_weapons()
        self.no_spawns()
        e = self.frozen_enemy("bat", 4)
        hp0 = self.game.hero_hp
        self.game.update(STEP)
        self.assertEqual(self.game.hero_hp, hp0 - e.damage)
        run(self.game, 0.2)  # still inside the cooldown
        self.assertEqual(self.game.hero_hp, hp0 - e.damage)
        run(self.game, 0.4)
        self.assertEqual(self.game.hero_hp, hp0 - 2 * e.damage)

    def test_game_over_and_play_again(self):
        self.no_weapons()
        self.no_spawns()
        self.frozen_enemy("bat", 4)
        self.game.hero_hp = 1
        run(self.game, 0.1)
        self.assertEqual(self.game.state, "lost")
        self.assertEqual(self.game.hero_hp, 0)
        run(self.game, 0.5)  # a lost game just stands still
        self.assertEqual(self.game.state, "lost")
        self.game.reset()
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.hero_hp, self.data["hero"]["hp"])
        self.assertEqual(self.game.kills, 0)


class TestGrowth(TestBase):
    def test_a_dead_enemy_drops_a_gem_worth_its_xp(self):
        self.no_spawns()
        e = self.frozen_enemy("bat")
        e.x, e.y = self.game.hero_x + 40, self.game.hero_y
        run(self.game, 2.0)
        self.assertTrue(e.dead)
        self.assertEqual(self.game.kills, 1)
        # the magnet radius (60 px) pulled the gem in and it was collected
        self.assertEqual(self.game.xp, self.data["enemies"]["bat"]["xp"])
        self.assertEqual(len(self.game.gems), 0)

    def test_xp_needed_grows_by_three(self):
        xp = self.data["xp"]
        self.assertEqual(self.game.xp_needed(1), xp["base"])
        self.assertEqual(self.game.xp_needed(2), xp["base"] + xp["per_level"])
        self.assertEqual(self.game.xp_needed(4), xp["base"] + 3 * xp["per_level"])

    def test_levelup_pauses_and_shows_cards(self):
        self.no_weapons()
        self.no_spawns()
        self.game.xp = self.game.xp_needed(1)
        run(self.game, STEP)
        self.assertEqual(self.game.state, "levelup")
        self.assertEqual(len(self.game.cards), self.data["levelup"]["cards"])
        for card in self.game.cards:
            name, lvl, line = self.game.card_text(card)
            self.assertTrue(name and line)
        run(self.game, 0.5)  # the world stands still while you choose
        self.assertEqual(self.game.state, "levelup")
        self.game.choose_card(0)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.level, 2)

    def test_the_three_weapons_and_three_items_all_work(self):
        self.no_spawns()
        d = self.data
        # Swift Boots: +10% walking speed per level
        self.game.passives["boots"] = 1
        self.assertAlmostEqual(self.game.hero_speed(),
                               d["hero"]["speed"] * 1.1, delta=0.01)
        # Big Heart: +20 max HP and heal 20
        hp0, max0 = self.game.hero_hp, self.game.hero_max_hp
        self.game.state = "levelup"
        self.game.cards = [("passive", "heart")]
        self.game.choose_card(0)
        self.assertEqual(self.game.hero_max_hp, max0 + d["passives"]["heart"]["max_hp_bonus"])
        self.assertEqual(self.game.hero_hp, hp0 + d["passives"]["heart"]["heal"])
        # Magnet: +30 px gem pickup
        self.game.passives["magnet"] = 2
        self.assertEqual(self.game.hero_magnet_radius(),
                         d["hero"]["magnet_radius"] + 2 * d["passives"]["magnet"]["magnet_bonus"])
        # Spark Wand levels: more damage, faster, +1 spark at levels 3 and 5
        w = self.game.weapons[0]
        spec = d["weapons"]["spark"]
        w.level = 5
        self.assertEqual(self.game.spark_count(w), 3)
        self.assertEqual(self.game.spark_damage(w), spec["damage"] + 4 * spec["damage_per_level"])
        self.assertAlmostEqual(self.game.spark_interval(w),
                               spec["interval"] - 4 * spec["interval_per_level"], delta=1e-6)

    def test_spin_blades_respect_the_per_enemy_cooldown(self):
        from rules import Weapon
        self.no_spawns()
        spec = self.data["weapons"]["blades"]
        w = Weapon("blades")
        w.level = 4                      # 4 blades -> one of them passes this enemy every 0.375 s
        self.game.weapons = [w]
        self.assertEqual(self.game.blade_count(w), spec["count"] + 2)
        e = self.frozen_enemy("bat")
        e.hp = 1000
        run(self.game, 2.0)
        per_hit = self.game.blade_damage(w)          # level 4 hits harder than level 1
        self.assertEqual(per_hit, spec["damage"] + 3 * spec["damage_per_level"])
        hits = (1000 - e.hp) // per_hit
        self.assertGreaterEqual(hits, 3)                               # the blades do hit
        self.assertLessEqual(hits, int(2.0 / spec["hit_cooldown"]))    # but not faster than 0.5 s

    def test_holy_ring_hurts_everything_inside_the_radius(self):
        from rules import Weapon
        self.no_spawns()
        self.game.weapons = [Weapon("ring")]
        spec = self.data["weapons"]["ring"]
        inside = self.frozen_enemy("bat", spec["radius"] - 10)
        outside = self.frozen_enemy("bat", spec["radius"] + 40)
        inside.hp = outside.hp = 100
        run(self.game, 0.7)  # the ring pulses at 0 s and at 0.5 s
        self.assertEqual(inside.hp, 100 - 2 * spec["damage"])
        self.assertEqual(outside.hp, 100)

    def test_cards_never_offer_something_maxed(self):
        from rules import Weapon
        d = self.data
        self.game.weapons = []
        for kind, spec in d["weapons"].items():
            w = Weapon(kind)
            w.level = spec["max_level"]
            self.game.weapons.append(w)
        for kind, spec in d["passives"].items():
            self.game.passives[kind] = spec["max_level"]
        self.assertEqual(self.game.card_options(), [("heal", None)])
        self.game.hero_hp = 10
        self.game.state = "levelup"
        self.game.cards = [("heal", None)]
        self.game.choose_card(0)
        self.assertEqual(self.game.hero_hp, 10 + d["levelup"]["heal"])
        self.assertLessEqual(self.game.hero_hp, self.game.hero_max_hp)

    def test_at_most_three_weapons(self):
        from rules import Weapon
        cap = self.data["levelup"]["max_weapons"]
        self.game.weapons = [Weapon(k) for k in list(self.data["weapons"])[:cap]]
        kinds = [c for c in self.game.card_options() if c[0] == "new_weapon"]
        self.assertEqual(kinds, [])


    def test_the_hero_can_outrun_every_normal_enemy(self):
        """No normal enemy may be faster than the hero's base speed: if one is,
        you can never shake it off without Boots. Ghosts used to be 135 px/s and
        a good kiting bot lost half its runs before the first Boots appeared."""
        for kind, spec in self.data["enemies"].items():
            if not spec.get("boss", False):
                self.assertLess(spec["speed"], self.data["hero"]["speed"], kind)


class TestWaves(TestBase):
    def test_the_wave_table_decides_who_comes(self):
        self.no_weapons()
        for t, types in ((0, ["bat"]), (30, ["bat", "slime"]), (45, ["slime", "ghost"]),
                         (60, ["bat", "ghost"]), (105, ["bat"])):
            self.game.time = t
            self.assertEqual(self.game.current_wave()["types"], types)
        self.game.time = 45
        self.game.spawn_timer = 0.0
        run(self.game, 1.0)
        self.assertTrue(all(e.kind in ("slime", "ghost") for e in self.game.enemies))

    def test_the_boss_comes_once_at_130_and_is_never_removed(self):
        self.no_weapons()
        self.game.time = 90.0
        self.game.spawn_timer = 0.0
        self.game.update(STEP)
        self.assertTrue(self.game.boss_spawned)
        boss = [e for e in self.game.enemies if e.is_boss]
        self.assertEqual(len(boss), 1)
        # left far behind: a normal enemy would be removed, the boss is moved back
        boss[0].x = self.game.hero_x + 900
        boss[0].y = self.game.hero_y
        self.game.update(STEP)
        self.assertIn(boss[0], self.game.enemies)
        d = ((boss[0].x - self.game.hero_x) ** 2 + (boss[0].y - self.game.hero_y) ** 2) ** 0.5
        self.assertAlmostEqual(d, self.data["spawning"]["circle_radius"], delta=3.0)
        # and it only appears once
        self.game.time = 105.0
        self.game.spawn_timer = 0.0
        self.game.update(STEP)
        self.assertEqual(len([e for e in self.game.enemies if e.is_boss]), 1)

    def test_never_more_than_max_alive(self):
        self.no_weapons()
        self.data = dict(self.data)
        self.data["waves"] = [dict(self.data["waves"][0], min_alive=self.data["spawning"]["max_alive"] + 50)]
        self.game.data = self.data
        run(self.game, 20.0)
        self.assertLessEqual(len(self.game.enemies), self.data["spawning"]["max_alive"])

    def test_win_at_two_minutes(self):
        self.no_weapons()
        self.game.time = self.data["win_time"] - STEP
        self.game.update(STEP)
        self.assertEqual(self.game.state, "won")


class TestWords(TestBase):
    """Every string on the screen comes from data/text.json, in both languages."""

    def test_both_languages_offer_the_same_keys(self):
        from rules import load_text
        text = load_text()
        self.assertEqual(sorted(text["en"]), sorted(text["zh"]))
        for lang in ("en", "zh"):
            self.assertEqual(sorted(text[lang]["names"]),
                             sorted(list(self.data["weapons"]) + list(self.data["passives"])))
            self.assertEqual(sorted(text[lang]["short"]), sorted(text[lang]["names"]))
            self.assertEqual(sorted(text[lang]["lines"]),
                             sorted(list(text[lang]["names"]) + ["heal"]))

    def test_every_card_reads_well_in_both_languages(self):
        for lang in ("en", "zh"):
            self.game.set_language(lang)
            for kind, spec in self.data["weapons"].items():
                for lvl in range(1, spec["max_level"] + 1):
                    line = self.game._weapon_line(kind, lvl)
                    self.assertTrue(line, (lang, kind, lvl))
                    self.assertNotIn("{", line)
            for kind in self.data["passives"]:
                name, lvl_txt, line = self.game.card_text(("passive", kind))
                self.assertTrue(name and lvl_txt and line, (lang, kind))
                self.assertNotIn("{", line)
            name, _lvl, line = self.game.card_text(("heal", None))
            self.assertTrue(name and line)
            self.assertNotIn("{", line)

    def test_switching_language_keeps_the_numbers(self):
        spec = self.data["weapons"]["spark"]
        dmg = str(spec["damage"] + spec["damage_per_level"])     # the Lv 2 damage
        self.game.set_language("zh")
        zh = self.game.card_text(("upgrade_weapon", "spark"))
        self.game.set_language("en")
        en = self.game.card_text(("upgrade_weapon", "spark"))
        self.assertNotEqual(zh[0], en[0])
        self.assertIn(dmg, zh[2])
        self.assertIn(dmg, en[2])
        self.assertFalse(self.game.set_language("de"))


if __name__ == "__main__":
    unittest.main()
