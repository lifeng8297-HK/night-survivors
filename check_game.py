"""Temporary check: run main.py headless for a few seconds with fake input.

main.py ends with asyncio.run(main()), so importing it would start the game and
never come back. We run it with runpy instead and post the fake events from a
second thread, so the input code in main.py really runs.
"""
import os
import runpy
import sys
import threading
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import pygame  # noqa: E402

W, H = 390, 700
SECONDS = 4.0


def inject():
    while not (pygame.get_init() and pygame.display.get_surface()):
        time.sleep(0.05)
    print("pygame ready, posting fake mouse moves, clicks and finger touches")
    frames = int(SECONDS * 60)
    for i in range(frames):
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(i % W, 100 + (i * 3) % (H - 200))))
        if i % 40 == 0:
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(W // 2, H // 2), button=1))
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(W // 2, H // 2), button=1))
            pygame.event.post(pygame.event.Event(pygame.FINGERDOWN, x=0.5, y=0.5, finger_id=0, touch_id=0))
            pygame.event.post(pygame.event.Event(pygame.FINGERMOTION, x=0.4, y=0.6, finger_id=0, touch_id=0))
            pygame.event.post(pygame.event.Event(pygame.FINGERUP, x=0.4, y=0.6, finger_id=0, touch_id=0))
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
        time.sleep(1 / 60)
    pygame.event.post(pygame.event.Event(pygame.QUIT))


threading.Thread(target=inject, daemon=True).start()
runpy.run_path(os.path.join(BASE_DIR, "main.py"), run_name="__main__")
print("check finished without errors")
