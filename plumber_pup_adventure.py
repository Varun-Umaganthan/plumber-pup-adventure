"""
Plumber Jump & Rescue Pup Squad
--------------------------------
A single continuous 10-level platform-jumping adventure.

Levels 1-5 : "Plumber Jump"       - a jumping hero dodges obstacles and enemies
Levels 6-10: "Rescue Pup Squad"   - a rescue pup dodges hazards to reach the doghouse

One click plays straight through all 10 levels in order.

Controls:
    LEFT / A    - move left
    RIGHT / D   - move right
    SPACE / UP  - jump
    P           - pause
    R           - restart (after game over or full completion)
    ESC / Q     - quit

Rules:
    - Reach the flag / doghouse at the end of each level to advance.
    - Falling into a gap or touching a hazard costs a life and restarts the level.
    - Landing ON TOP of an enemy defeats it and bounces you up.
    - Touching an enemy from the side costs a life.
    - Collect coins / bones for bonus score.
    - You have 3 lives for the whole run.
"""

import asyncio
import pygame
import random
import sys

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
pygame.init()

WIDTH, HEIGHT = 900, 500
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Plumber Jump & Rescue Pup Squad")
CLOCK = pygame.time.Clock()
FPS = 60

GRAVITY = 0.8
JUMP_STRENGTH = -14.5
MOVE_SPEED = 5.2
GROUND_Y = HEIGHT - 90

TOTAL_LEVELS = 10
LEVELS_PER_THEME = 5

WHITE = (255, 255, 255)
BLACK = (25, 25, 25)
DARK = (40, 40, 45)
GRAY_TEXT = (210, 210, 215)
GOLD = (250, 210, 90)
RED = (215, 60, 60)

FONT_BIG = pygame.font.Font(None, 54)
FONT_MED = pygame.font.Font(None, 32)
FONT_SMALL = pygame.font.Font(None, 24)

# ---------------------------------------------------------------------------
# Theme palettes
# ---------------------------------------------------------------------------
THEMES = {
    "plumber": {
        "name": "Plumber Jump",
        "sky_top": (110, 180, 245),
        "sky_bottom": (175, 220, 255),
        "ground": (150, 100, 60),
        "ground_top": (90, 170, 70),
        "platform": (170, 120, 75),
        "player_body": (200, 40, 40),
        "player_accent": (250, 210, 90),
        "enemy": (120, 80, 50),
        "coin": (250, 210, 60),
        "hazard": (60, 170, 90),
        "goal": (60, 170, 90),
    },
    "pup": {
        "name": "Rescue Pup Squad",
        "sky_top": (255, 200, 120),
        "sky_bottom": (255, 235, 190),
        "ground": (210, 170, 120),
        "ground_top": (240, 200, 150),
        "platform": (230, 190, 140),
        "player_body": (240, 150, 40),
        "player_accent": (255, 255, 255),
        "enemy": (120, 120, 130),
        "coin": (230, 210, 200),
        "hazard": (90, 150, 220),
        "goal": (220, 60, 60),
    },
}


def theme_for_level(level_num):
    return "plumber" if level_num <= LEVELS_PER_THEME else "pup"


_BACKGROUND_CACHE = {}


# ---------------------------------------------------------------------------
# Level generation (procedural, seeded so each level is consistent)
# ---------------------------------------------------------------------------
class LevelData:
    def __init__(self, level_num):
        self.level_num = level_num
        self.theme = theme_for_level(level_num)
        tier = level_num if level_num <= LEVELS_PER_THEME else level_num - LEVELS_PER_THEME

        rng = random.Random(1000 + level_num)
        self.width = 2100 + tier * 220

        self.ground_segments = []   # list of (x_start, x_end)
        self.gaps = []               # list of (x_start, x_end)
        self.platforms = []          # list of pygame.Rect (floating platforms)
        self.enemies_init = []       # list of dicts: x, y, range, speed
        self.coins = []               # list of [x, y, collected]
        self.hazards = []            # list of pygame.Rect (instant-death strips)

        x = 260  # safe starting zone
        gaps_remaining = 2 + tier
        enemies_remaining = 2 + tier

        while x < self.width - 320:
            seg_len = rng.randint(190, 330)
            self.ground_segments.append((x, x + seg_len))

            # maybe place an enemy on this ground segment
            if enemies_remaining > 0 and seg_len > 150 and rng.random() < 0.65:
                ex = x + rng.randint(60, seg_len - 60)
                patrol_range = rng.randint(40, 90)
                self.enemies_init.append({
                    "x": ex, "y": GROUND_Y - 34, "left": ex - patrol_range,
                    "right": ex + patrol_range, "speed": 1.4 + tier * 0.15, "dir": 1,
                })
                enemies_remaining -= 1

            # maybe place a coin on this ground segment
            if rng.random() < 0.8:
                cx = x + rng.randint(40, seg_len - 40) if seg_len > 80 else x + seg_len // 2
                self.coins.append([cx, GROUND_Y - 60, False])

            x += seg_len

            if gaps_remaining > 0 and rng.random() < 0.6:
                gap_len = rng.randint(80, 90 + tier * 8)
                self.gaps.append((x, x + gap_len))

                # sometimes add a floating platform to help cross, sometimes a hazard strip
                if rng.random() < 0.55:
                    plat_w = max(70, gap_len - 10)
                    plat_y = GROUND_Y - rng.randint(70, 130)
                    self.platforms.append(pygame.Rect(x + (gap_len - plat_w) // 2, plat_y, plat_w, 22))
                    self.coins.append([x + gap_len // 2, plat_y - 30, False])
                else:
                    self.hazards.append(pygame.Rect(x, GROUND_Y + 40, gap_len, 20))

                x += gap_len
                gaps_remaining -= 1

        # final stretch of solid ground leading to the goal
        self.ground_segments.append((x, self.width))
        self.goal_x = self.width - 140

        # a couple of decorative floating platforms with coins mid-level
        for _ in range(1 + tier // 2):
            px = rng.randint(400, self.width - 400)
            py = GROUND_Y - rng.randint(90, 160)
            pw = rng.randint(90, 150)
            self.platforms.append(pygame.Rect(px, py, pw, 22))
            self.coins.append([px + pw // 2, py - 30, False])

    def is_over_gap(self, x):
        for gx0, gx1 in self.gaps:
            if gx0 <= x <= gx1:
                return True
        return False


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, start_x):
        self.w, self.h = 34, 48
        self.start_x = start_x
        self.reset(start_x)

    def reset(self, x):
        self.x = float(x)
        self.y = float(GROUND_Y - self.h)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.facing = 1

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def handle_input(self, keys):
        self.vx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vx = -MOVE_SPEED
            self.facing = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vx = MOVE_SPEED
            self.facing = 1
        if (keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]) and self.on_ground:
            self.vy = JUMP_STRENGTH
            self.on_ground = False

    def physics_step(self, level):
        # horizontal move
        self.x += self.vx
        self.x = max(0, min(self.x, level.width - self.w))

        # gravity
        self.vy += GRAVITY
        self.y += self.vy
        self.on_ground = False

        feet = self.y + self.h
        cx = self.x + self.w / 2

        # ground segments
        for gx0, gx1 in level.ground_segments:
            if gx0 <= cx <= gx1:
                if feet >= GROUND_Y and self.vy >= 0:
                    self.y = GROUND_Y - self.h
                    self.vy = 0
                    self.on_ground = True

        # floating platforms (one-way, land on top only)
        for plat in level.platforms:
            if plat.left <= cx <= plat.right:
                if self.vy >= 0 and feet >= plat.top and (feet - self.vy) <= plat.top + 6:
                    self.y = plat.top - self.h
                    self.vy = 0
                    self.on_ground = True

    def draw(self, surface, camera_x, theme_key):
        pal = THEMES[theme_key]
        sx = int(self.x - camera_x)
        sy = int(self.y)
        body = pygame.Rect(sx, sy, self.w, self.h)
        pygame.draw.rect(surface, pal["player_body"], body, border_radius=10)
        # head/cap or ears accent
        pygame.draw.rect(surface, pal["player_accent"], (sx + 4, sy + 4, self.w - 8, 12), border_radius=6)
        # eyes
        eye_x = sx + (self.w - 10 if self.facing > 0 else 4)
        pygame.draw.circle(surface, WHITE, (eye_x + 4, sy + 20), 5)
        pygame.draw.circle(surface, BLACK, (eye_x + 4 + (2 * self.facing), sy + 20), 2)
        # legs
        pygame.draw.rect(surface, DARK, (sx + 4, sy + self.h - 10, 10, 10), border_radius=3)
        pygame.draw.rect(surface, DARK, (sx + self.w - 14, sy + self.h - 10, 10, 10), border_radius=3)


class Enemy:
    def __init__(self, data):
        self.x = float(data["x"])
        self.y = float(data["y"])
        self.left = data["left"]
        self.right = data["right"]
        self.speed = data["speed"]
        self.dir = data["dir"]
        self.w, self.h = 30, 30
        self.alive = True

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y - self.h / 2), self.w, self.h)

    def update(self):
        if not self.alive:
            return
        self.x += self.speed * self.dir
        if self.x < self.left:
            self.x = self.left
            self.dir = 1
        elif self.x > self.right:
            self.x = self.right
            self.dir = -1

    def draw(self, surface, camera_x, theme_key):
        if not self.alive:
            return
        pal = THEMES[theme_key]
        sx = int(self.x - camera_x)
        sy = int(self.y)
        pygame.draw.ellipse(surface, pal["enemy"], (sx - 15, sy - 15, 30, 30))
        pygame.draw.circle(surface, WHITE, (sx - 5, sy - 4), 4)
        pygame.draw.circle(surface, WHITE, (sx + 5, sy - 4), 4)
        pygame.draw.circle(surface, BLACK, (sx - 5, sy - 4), 2)
        pygame.draw.circle(surface, BLACK, (sx + 5, sy - 4), 2)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def draw_background(surface, theme_key, camera_x):
    pal = THEMES[theme_key]

    bg = _BACKGROUND_CACHE.get(theme_key)
    if bg is None:
        bg = pygame.Surface((WIDTH, HEIGHT))
        for i in range(HEIGHT):
            t = i / HEIGHT
            r = pal["sky_top"][0] + (pal["sky_bottom"][0] - pal["sky_top"][0]) * t
            g = pal["sky_top"][1] + (pal["sky_bottom"][1] - pal["sky_top"][1]) * t
            b = pal["sky_top"][2] + (pal["sky_bottom"][2] - pal["sky_top"][2]) * t
            pygame.draw.line(bg, (r, g, b), (0, i), (WIDTH, i))
        _BACKGROUND_CACHE[theme_key] = bg

    surface.blit(bg, (0, 0))

    # parallax hills
    for i in range(-1, 6):
        hx = i * 260 - int(camera_x * 0.3) % 260
        pygame.draw.ellipse(surface, pal["ground_top"], (hx, HEIGHT - 220, 300, 200))

    # parallax clouds
    for i in range(-1, 5):
        cx = i * 300 - int(camera_x * 0.15) % 300
        cy = 60 + (i * 37) % 90
        pygame.draw.ellipse(surface, WHITE, (cx, cy, 90, 30))
        pygame.draw.ellipse(surface, WHITE, (cx + 30, cy - 12, 70, 30))


def draw_level(surface, level, camera_x, coins_state):
    pal = THEMES[level.theme]

    for gx0, gx1 in level.ground_segments:
        sx0 = gx0 - camera_x
        sx1 = gx1 - camera_x
        if sx1 < -50 or sx0 > WIDTH + 50:
            continue
        rect = pygame.Rect(sx0, GROUND_Y, sx1 - sx0, HEIGHT - GROUND_Y)
        pygame.draw.rect(surface, pal["ground"], rect)
        pygame.draw.rect(surface, pal["ground_top"], (sx0, GROUND_Y, sx1 - sx0, 14))

    for plat in level.platforms:
        sx = plat.x - camera_x
        if sx < -100 or sx > WIDTH + 100:
            continue
        pygame.draw.rect(surface, pal["platform"], (sx, plat.y, plat.width, plat.height), border_radius=6)

    for hz in level.hazards:
        sx = hz.x - camera_x
        if sx < -100 or sx > WIDTH + 100:
            continue
        pygame.draw.rect(surface, pal["hazard"], (sx, hz.y, hz.width, hz.height))

    for coin in coins_state:
        if coin[2]:
            continue
        sx = coin[0] - camera_x
        if -20 < sx < WIDTH + 20:
            pygame.draw.circle(surface, pal["coin"], (int(sx), int(coin[1])), 9)
            pygame.draw.circle(surface, GOLD, (int(sx), int(coin[1])), 9, 2)

    # goal marker
    gsx = level.goal_x - camera_x
    if -60 < gsx < WIDTH + 60:
        pygame.draw.rect(surface, DARK, (gsx, GROUND_Y - 130, 6, 130))
        if level.theme == "plumber":
            pygame.draw.polygon(surface, pal["goal"], [
                (gsx + 6, GROUND_Y - 130), (gsx + 46, GROUND_Y - 112), (gsx + 6, GROUND_Y - 94)
            ])
        else:
            pygame.draw.rect(surface, pal["goal"], (gsx - 24, GROUND_Y - 70, 60, 70), border_radius=8)
            pygame.draw.polygon(surface, DARK, [
                (gsx - 30, GROUND_Y - 70), (gsx + 6, GROUND_Y - 110), (gsx + 42, GROUND_Y - 70)
            ])


def draw_text_center(surface, text, font, color, cx, cy):
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=(cx, cy))
    surface.blit(surf, rect)


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------
async def game_loop():
    level_num = 1
    level = LevelData(level_num)
    player = Player(80)
    enemies = [Enemy(d) for d in level.enemies_init]
    coins_state = [c for c in level.coins]

    lives = 3
    score = 0
    camera_x = 0.0
    paused = False
    state = "playing"   # playing, level_transition, game_over, game_complete
    transition_timer = 0
    transition_text = ""

    def load_level(n):
        nonlocal level, player, enemies, coins_state, camera_x
        level = LevelData(n)
        player.reset(80)
        enemies = [Enemy(d) for d in level.enemies_init]
        coins_state = [c for c in level.coins]
        camera_x = 0.0

    def full_restart():
        nonlocal level_num, lives, score, state
        level_num = 1
        lives = 3
        score = 0
        state = "playing"
        load_level(level_num)

    running = True
    while running:
        CLOCK.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_p and state == "playing":
                    paused = not paused
                elif event.key == pygame.K_r and state in ("game_over", "game_complete"):
                    full_restart()

        keys = pygame.key.get_pressed()

        if state == "playing" and not paused:
            player.handle_input(keys)
            player.physics_step(level)

            for e in enemies:
                e.update()

            # camera follow
            camera_x = max(0, min(player.x - WIDTH / 3, level.width - WIDTH))

            # fell into a gap -> lose life
            if player.y > HEIGHT + 40:
                lives -= 1
                if lives <= 0:
                    state = "game_over"
                else:
                    load_level(level_num)

            # hazard collision -> lose life
            prect = player.rect
            for hz in level.hazards:
                if prect.colliderect(hz):
                    lives -= 1
                    if lives <= 0:
                        state = "game_over"
                    else:
                        load_level(level_num)
                    break

            # enemy collisions
            if state == "playing":
                for e in enemies:
                    if not e.alive:
                        continue
                    if prect.colliderect(e.rect):
                        falling_onto = player.vy > 0 and (prect.bottom - e.rect.top) < 20
                        if falling_onto:
                            e.alive = False
                            player.vy = JUMP_STRENGTH * 0.6
                            score += 50
                        else:
                            lives -= 1
                            if lives <= 0:
                                state = "game_over"
                            else:
                                load_level(level_num)
                            break

            # coin collection
            if state == "playing":
                for coin in coins_state:
                    if coin[2]:
                        continue
                    if abs((prect.centerx) - coin[0]) < 22 and abs((prect.centery) - coin[1]) < 22:
                        coin[2] = True
                        score += 10

            # reached goal
            if state == "playing" and player.x + player.w >= level.goal_x:
                score += 100
                if level_num >= TOTAL_LEVELS:
                    state = "game_complete"
                else:
                    next_theme = theme_for_level(level_num + 1)
                    cur_theme = theme_for_level(level_num)
                    if next_theme != cur_theme:
                        transition_text = f"{THEMES[cur_theme]['name']} complete! Entering {THEMES[next_theme]['name']}..."
                    else:
                        transition_text = f"Level {level_num} complete!"
                    level_num += 1
                    state = "level_transition"
                    transition_timer = 90

        elif state == "level_transition":
            transition_timer -= 1
            if transition_timer <= 0:
                load_level(level_num)
                state = "playing"

        # ---------------- draw ----------------
        draw_background(SCREEN, level.theme, camera_x)
        draw_level(SCREEN, level, camera_x, coins_state)
        for e in enemies:
            e.draw(SCREEN, camera_x, level.theme)
        player.draw(SCREEN, camera_x, level.theme)

        # HUD
        hud_text = f"{THEMES[level.theme]['name']}  -  Level {level_num}/{TOTAL_LEVELS}"
        SCREEN.blit(FONT_MED.render(hud_text, True, WHITE), (14, 12))
        SCREEN.blit(FONT_SMALL.render(f"Score: {score}", True, WHITE), (14, 46))
        SCREEN.blit(FONT_SMALL.render(f"Lives: {lives}", True, WHITE), (WIDTH - 110, 12))
        SCREEN.blit(FONT_SMALL.render("P: pause   ESC: quit", True, GRAY_TEXT), (14, HEIGHT - 26))

        if paused and state == "playing":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            SCREEN.blit(overlay, (0, 0))
            draw_text_center(SCREEN, "PAUSED", FONT_BIG, WHITE, WIDTH // 2, HEIGHT // 2 - 10)
            draw_text_center(SCREEN, "Press P to resume", FONT_SMALL, GRAY_TEXT, WIDTH // 2, HEIGHT // 2 + 30)

        if state == "level_transition":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            SCREEN.blit(overlay, (0, 0))
            draw_text_center(SCREEN, transition_text, FONT_MED, GOLD, WIDTH // 2, HEIGHT // 2)

        if state == "game_over":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            SCREEN.blit(overlay, (0, 0))
            draw_text_center(SCREEN, "GAME OVER", FONT_BIG, RED, WIDTH // 2, HEIGHT // 2 - 50)
            draw_text_center(SCREEN, f"Score: {score}", FONT_MED, WHITE, WIDTH // 2, HEIGHT // 2)
            draw_text_center(SCREEN, "Press R to restart or ESC to quit", FONT_SMALL, GRAY_TEXT, WIDTH // 2, HEIGHT // 2 + 40)

        if state == "game_complete":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            SCREEN.blit(overlay, (0, 0))
            draw_text_center(SCREEN, "ALL 10 LEVELS COMPLETE!", FONT_BIG, GOLD, WIDTH // 2, HEIGHT // 2 - 50)
            draw_text_center(SCREEN, f"Final Score: {score}", FONT_MED, WHITE, WIDTH // 2, HEIGHT // 2)
            draw_text_center(SCREEN, "Press R to play again or ESC to quit", FONT_SMALL, GRAY_TEXT, WIDTH // 2, HEIGHT // 2 + 40)

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    asyncio.run(game_loop())
