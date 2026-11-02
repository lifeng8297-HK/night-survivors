"""Night Survivors - window, drawing, sound and input.

The rules live in rules.py. This file only shows the game and passes input to it.
It loads finished files from assets/ and sounds/ (make_assets.py and make_sounds.py
make them on your computer). The main loop is async so pygbag can run it in a browser.
"""
import asyncio
import math
import os
import random

import pygame

from rules import Game, load_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE_DIR, "assets")
SOUNDS = os.path.join(BASE_DIR, "sounds")

ENEMY_IMAGES = {"bat": "bat.png", "slime": "slime.png", "ghost": "ghost.png", "demon": "demon.png"}

FALLBACK_TILE = 48             # only used before make_assets.py has run
FLOOR_A = (40, 43, 66)
FLOOR_B = (32, 35, 56)
HERO_COLOR = (90, 200, 255)
ENEMY_COLOR = (176, 96, 208)
SPARK_COLOR = (255, 240, 120)
GEM_SIZE = 24                  # a pickup should look small, the art itself is 48 px

# pygame's built-in font has no Chinese glyphs, so Chinese needs a system font.
CJK_FONTS = ("simhei", "microsoftyahei", "dengxian", "notosanscjksc", "pingfangsc")


def cjk_font_path():
    for name in CJK_FONTS:
        path = pygame.font.match_font(name)
        if path:
            return path
    return None


def font_can_draw_chinese(font, sample):
    """A missing glyph is only a few px wide; a real one fills the whole em."""
    return font.size(sample)[0] >= font.get_height() - 8


def make_fonts(path):
    def one(size):
        return pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
    return one(22), one(64), one(34)


def wrap(text, font, max_w):
    """Break a line so it fits the card. Chinese words have no spaces, so one
    Chinese character is a unit of its own while ASCII runs stay together."""
    units, run = [], ""
    for ch in text:
        if ch == " " or ord(ch) > 127:
            if run:
                units.append(run)
                run = ""
            units.append(ch)
        else:
            run += ch
    if run:
        units.append(run)
    rows, row = [], ""
    for unit in units:
        if row and font.size(row + unit)[0] > max_w:
            rows.append(row.rstrip())
            row = unit.lstrip()
        else:
            row += unit
    rows.append(row.rstrip())
    return rows


def load_image(name, size=None):
    """A finished picture from assets/, or None if make_assets.py has not run yet."""
    path = os.path.join(ASSETS, name)
    if not os.path.exists(path):
        return None
    img = pygame.image.load(path).convert_alpha()
    if size is not None:
        img = pygame.transform.scale(img, (size, size))
    return img


def load_sound(name):
    for ext in (".ogg", ".wav"):
        path = os.path.join(SOUNDS, name + ext)
        if os.path.exists(path):
            return pygame.mixer.Sound(path)
    return None


def fmt_time(t):
    t = max(0, int(t))
    return "%d:%02d" % (t // 60, t % 60)


class Effects:
    """Damage numbers, death flashes and the small shake when you are hurt."""

    def __init__(self):
        self.numbers = []   # {x, y, text, t}
        self.flashes = []   # {x, y, t}
        self.shake = 0.0

    def clear(self):
        self.__init__()

    def update(self, dt):
        for n in self.numbers:
            n["y"] -= 40 * dt
            n["t"] -= dt
        self.numbers = [n for n in self.numbers if n["t"] > 0]
        for f in self.flashes:
            f["t"] -= dt
        self.flashes = [f for f in self.flashes if f["t"] > 0]
        self.shake = max(0.0, self.shake - dt)

    def hurt_shake(self):
        self.shake = 0.25


async def main():
    data = load_data()
    W = data["screen"]["width"]
    H = data["screen"]["height"]
    win_time = data["win_time"]

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    try:
        pygame.mixer.init()
        sounds = {name: load_sound(name) for name in ("shoot", "hit", "gem", "levelup", "hurt", "end")}
    except pygame.error:
        sounds = {}

    game = Game(data, seed=random.randint(0, 10**9))
    fonts = {"en": make_fonts(None)}
    probe = game.text_all["probe"]
    cjk = cjk_font_path()
    if cjk and font_can_draw_chinese(pygame.font.Font(cjk, 22), probe):
        fonts["zh"] = make_fonts(cjk)
    elif game.lang == "zh":
        game.set_language("en")        # no Chinese font here, so show the English words
    pygame.display.set_caption(game.T["title"])

    images = {kind: load_image(file) for kind, file in ENEMY_IMAGES.items()}
    images["hero"] = load_image("hero.png")
    images["sword"] = load_image("sword.png")
    images["gem_blue"] = load_image("gem_blue.png", GEM_SIZE)
    images["gem_pink"] = load_image("gem_pink.png", GEM_SIZE)
    images["floor"] = load_image("floor.png")
    tile = images["floor"].get_width() if images["floor"] else FALLBACK_TILE

    fx = Effects()

    mouse_pos = (W // 2, H // 2)
    touch_pos = None
    card_rects = []
    accumulator = 0.0
    running = True

    def pick_card(pos):
        """A click or a tap on one of the level-up cards."""
        for i, rect in enumerate(card_rects):
            if rect.collidepoint(pos):
                game.choose_card(i)
                return

    while running:
        # 1 input
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                if game.state == "playing":
                    game.paused = not game.paused
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_l:
                other = "en" if game.lang == "zh" else "zh"
                if other in fonts and game.set_language(other):
                    pygame.display.set_caption(game.T["title"])
            elif event.type == pygame.MOUSEMOTION:
                mouse_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                if game.state == "levelup":
                    pick_card(event.pos)
                elif game.state in ("won", "lost"):
                    game.reset()
                    fx.clear()
            elif event.type == pygame.FINGERDOWN:
                touch_pos = (event.x * W, event.y * H)
                if game.state == "levelup":
                    pick_card(touch_pos)
                elif game.state in ("won", "lost"):
                    game.reset()
                    fx.clear()
            elif event.type == pygame.FINGERMOTION:
                touch_pos = (event.x * W, event.y * H)
            elif event.type == pygame.FINGERUP:
                touch_pos = None

        # the camera follows the hero, so the screen centre is always him
        cam_x = game.hero_x - W / 2
        cam_y = game.hero_y - H / 2

        # 2 update: the finger while it touches, otherwise the mouse pointer
        pointer = touch_pos if touch_pos is not None else mouse_pos
        game.move_target = (pointer[0] + cam_x, pointer[1] + cam_y)
        accumulator = min(accumulator + dt, game.step * 5)   # never catch up after a long pause
        while accumulator >= game.step:
            game.update()
            accumulator -= game.step

        # what the rules tell us to show and play
        for ev in game.events:
            kind = ev[0]
            if kind == "shoot" and sounds.get("shoot"):
                sounds["shoot"].play()
            elif kind == "hit":
                fx.numbers.append({"x": ev[1], "y": ev[2], "text": str(ev[3]), "t": 0.7})
                if sounds.get("hit"):
                    sounds["hit"].play()
            elif kind == "enemy_die":
                fx.flashes.append({"x": ev[1], "y": ev[2], "t": 0.3})
            elif kind == "gem" and sounds.get("gem"):
                sounds["gem"].play()
            elif kind == "hurt":
                fx.hurt_shake()
                if sounds.get("hurt"):
                    sounds["hurt"].play()
            elif kind == "levelup" and sounds.get("levelup"):
                sounds["levelup"].play()
            elif kind in ("win", "lose") and sounds.get("end"):
                sounds["end"].play()
        fx.update(dt)

        # 3 draw
        font, big_font, mid_font = fonts[game.lang]
        sx = sy = 0
        if fx.shake > 0:
            sx = random.randint(-4, 4)
            sy = random.randint(-4, 4)
        cam_x += sx
        cam_y += sy

        screen.fill(FLOOR_A)
        # one tile repeated forever: the map has no edges
        x0 = int(math.floor(cam_x / tile)) * tile
        y0 = int(math.floor(cam_y / tile)) * tile
        for tx in range(x0, int(cam_x) + W + tile, tile):
            for ty in range(y0, int(cam_y) + H + tile, tile):
                if images["floor"]:
                    screen.blit(images["floor"], (tx - cam_x, ty - cam_y))
                elif ((tx // tile) + (ty // tile)) % 2:
                    pygame.draw.rect(screen, FLOOR_B, (tx - cam_x, ty - cam_y, tile, tile))

        def to_screen(x, y):
            return (int(x - cam_x), int(y - cam_y))

        for g in game.gems:
            img = images["gem_pink"] if g.value >= 2 else images["gem_blue"]
            pos = to_screen(g.x, g.y)
            if img:
                screen.blit(img, img.get_rect(center=pos))
            else:
                color = (255, 100, 200) if g.value >= 2 else (100, 160, 255)
                pygame.draw.circle(screen, color, pos, 5)

        for w in game.weapons:
            if w.kind == "ring":
                pygame.draw.circle(screen, (255, 220, 100),
                                   to_screen(game.hero_x, game.hero_y), game.ring_radius(w), 2)

        for e in game.enemies:
            pos = to_screen(e.x, e.y)
            img = images.get(e.kind)
            if img:
                screen.blit(img, img.get_rect(center=pos))
            else:
                pygame.draw.circle(screen, ENEMY_COLOR, pos, e.radius)

        for s in game.sparks:
            pygame.draw.circle(screen, SPARK_COLOR, to_screen(s.x, s.y),
                               data["weapons"]["spark"]["spark_radius"])

        # Spin Blades: swords on a circle around the hero, pointing outward
        for w in game.weapons:
            if w.kind != "blades":
                continue
            spec = data["weapons"]["blades"]
            n = game.blade_count(w)
            for i in range(n):
                a = w.angle + math.tau * i / n
                bx = game.hero_x + math.cos(a) * spec["orbit_radius"]
                by = game.hero_y + math.sin(a) * spec["orbit_radius"]
                pos = to_screen(bx, by)
                img = images["sword"]
                if img:
                    rot = pygame.transform.rotate(img, -math.degrees(a) - 90)
                    screen.blit(rot, rot.get_rect(center=pos))
                else:
                    pygame.draw.circle(screen, (220, 220, 235), pos, spec["blade_radius"])

        hpos = to_screen(game.hero_x, game.hero_y)
        if images["hero"]:
            screen.blit(images["hero"], images["hero"].get_rect(center=hpos))
        else:
            pygame.draw.circle(screen, HERO_COLOR, hpos, data["hero"]["hit_radius"])

        # death flashes and damage numbers
        for f in fx.flashes:
            t = 1 - f["t"] / 0.3
            pygame.draw.circle(screen, (255, 255, 255), to_screen(f["x"], f["y"]),
                               int(6 + 22 * t), 2)
        for n in fx.numbers:
            col = (255, 255, 160) if n["t"] > 0.35 else (255, 160, 80)
            img = font.render(n["text"], True, col)
            screen.blit(img, img.get_rect(center=to_screen(n["x"], n["y"])))

        # -- user interface
        bar_w = 140
        hp_frac = max(0.0, game.hero_hp / game.hero_max_hp)
        pygame.draw.rect(screen, (60, 60, 70), (10, 10, bar_w, 14))
        pygame.draw.rect(screen, (220, 60, 60), (10, 10, int(bar_w * hp_frac), 14))
        xp_frac = min(1.0, game.xp / game.xp_needed(game.level))
        pygame.draw.rect(screen, (60, 60, 70), (10, 28, bar_w, 10))
        pygame.draw.rect(screen, (80, 140, 255), (10, 28, int(bar_w * xp_frac), 10))
        lv = font.render(game.T["level"].format(n=game.level), True, (240, 240, 240))
        screen.blit(lv, (10, 42))

        timer = font.render(fmt_time(game.time) + " / " + fmt_time(win_time), True, (240, 240, 240))
        screen.blit(timer, timer.get_rect(topright=(W - 10, 10)))

        short = game.T["short"]
        parts = ["%s %d" % (short[w.kind], w.level) for w in game.weapons]
        parts += ["%s %d" % (short[k], lvl) for k, lvl in sorted(game.passives.items())]
        have = font.render("  ".join(parts), True, (220, 220, 220))
        screen.blit(have, have.get_rect(midbottom=(W // 2, H - 8)))

        if game.paused and game.state == "playing":
            img = mid_font.render(game.T["paused"], True, (255, 255, 255))
            screen.blit(img, img.get_rect(center=(W // 2, H // 2)))

        if game.state == "levelup":
            dim = pygame.Surface((W, H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 160))
            screen.blit(dim, (0, 0))
            card_rects = []
            cw, ch = 116, 170
            gap = 8
            total = len(game.cards) * cw + (len(game.cards) - 1) * gap
            x = (W - total) // 2
            y = H // 2 - ch // 2
            for i, card in enumerate(game.cards):
                rect = pygame.Rect(x + i * (cw + gap), y, cw, ch)
                card_rects.append(rect)
                pygame.draw.rect(screen, (45, 45, 60), rect, border_radius=8)
                pygame.draw.rect(screen, (140, 140, 180), rect, 2, border_radius=8)
                title, lvl_txt, line = game.card_text(card)
                timg = font.render(title, True, (255, 255, 255))
                screen.blit(timg, timg.get_rect(center=(rect.centerx, rect.y + 30)))
                if lvl_txt:
                    limg = font.render(lvl_txt, True, (150, 200, 255))
                    screen.blit(limg, limg.get_rect(center=(rect.centerx, rect.y + 60)))
                rows = wrap(line, font, cw - 14)
                for j, rtext in enumerate(rows):
                    rimg = font.render(rtext, True, (210, 210, 210))
                    screen.blit(rimg, rimg.get_rect(center=(rect.centerx, rect.y + 95 + j * 20)))

        if game.state in ("won", "lost"):
            dim = pygame.Surface((W, H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 180))
            screen.blit(dim, (0, 0))
            msg = game.T["victory"] if game.state == "won" else game.T["game_over"]
            color = (120, 255, 140) if game.state == "won" else (255, 90, 90)
            img = big_font.render(msg, True, color)
            screen.blit(img, img.get_rect(center=(W // 2, H // 2 - 70)))
            stats = font.render(game.T["stats"].format(time=fmt_time(game.time),
                                                      kills=game.kills, level=game.level),
                                True, (240, 240, 240))
            screen.blit(stats, stats.get_rect(center=(W // 2, H // 2)))
            tip = font.render(game.T["again"], True, (180, 180, 180))
            screen.blit(tip, tip.get_rect(center=(W // 2, H // 2 + 40)))

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


asyncio.run(main())
