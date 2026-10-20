# Whack-a-Mole: the few commands used at the bench and in the field.
# Run `make` for the list. Nothing here flashes or runs by itself.
#
# Box names are YOUR view: standing where the player stands, facing the boxes.
# The firmware names the boxes from BEHIND them, so the builds are flipped:
#
#   make target | your box | tracker node | build env   | x in tracker frame
#   left        | left     | 2            | node_right  | 1.50 m
#   middle      | middle   | 1            | node_middle | 0.75 m  (buzzer box)
#   right       | right    | 0            | node_left   | 0.00 m
#   fourth      | fourth   | 3            | node_fourth | 0.85 m  (player versus player)
#
# Plug ONE box in at a time. PORT is found by itself (/dev/ttyUSB0 and so on);
# override with `make left PORT=/dev/ttyUSB1`. MONITOR=0 skips the serial
# monitor after an upload. The firmware built is whatever this checkout holds:
# `make status` shows the commit before you flash.

.RECIPEPREFIX = >
SHELL := /bin/bash

PIO           ?= $(HOME)/.platformio/penv/bin/pio
FIRMWARE      := $(CURDIR)/firmware
GAME          ?= $(HOME)/Desktop/ENGG3000_Group2_WhackAMole
GAME_PY       ?= $(GAME)/.venv/bin/python
PORT          ?= $(firstword $(wildcard /dev/ttyUSB* /dev/ttyACM*))
MONITOR       ?= 1
CONFIG_LOCAL  := $(FIRMWARE)/include/config.local.h
CONFIG_BACKUP ?= $(HOME)/tracker-private-backup-2026-10-02/firmware/include/config.local.h

.DEFAULT_GOAL := help
.PHONY: help left middle right fourth upload monitor ports build config status \
        game game-pygame game-sim tracker tracker-pvp tracker-sim test test-game test-tracker update

help: ## This list
> @echo "Boxes (your view):"
> @grep -E '^(left|middle|right|fourth|monitor|ports|build|status):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo "Game and tracker:"
> @grep -E '^(game|game-pygame|game-sim|tracker|tracker-pvp|tracker-sim):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo "Housekeeping:"
> @grep -E '^(test|test-game|test-tracker|update):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo
> @echo "Box table (your view -> build): left=node_right  middle=node_middle  right=node_left  fourth=node_fourth"

# ---- boxes -----------------------------------------------------------------

left: ## Upload YOUR left box (tracker node 2, build node_right)
> @$(MAKE) --no-print-directory upload ENV=node_right NAME="left box (node 2)"

middle: ## Upload the middle box (node 1, build node_middle, buzzer)
> @$(MAKE) --no-print-directory upload ENV=node_middle NAME="middle box (node 1)"

right: ## Upload YOUR right box (tracker node 0, build node_left)
> @$(MAKE) --no-print-directory upload ENV=node_left NAME="right box (node 0)"

fourth: ## Upload the fourth box (node 3, build node_fourth, player versus player)
> @$(MAKE) --no-print-directory upload ENV=node_fourth NAME="fourth box (node 3)"

upload: config
> @test -n "$(PORT)" || { echo "No board found on /dev/ttyUSB* or /dev/ttyACM*. Plug the box in, or pass PORT=/dev/ttyUSBn"; exit 1; }
> @echo "== $(NAME): env $(ENV) on $(PORT), firmware at $$(git log -1 --format='%h %s')"
> @grep -q 'ESP32-Battery' $(FIRMWARE)/src/main.cpp && echo "   note: this build has the battery soft access point (WIFI_AP_STA)" || true
> cd $(FIRMWARE) && ($(PIO) run -e $(ENV) -t upload --upload-port $(PORT) || { echo "== first upload failed, trying once more"; $(PIO) run -e $(ENV) -t upload --upload-port $(PORT); })
> @echo "== uploaded $(NAME). Boot banner must say the node number above."
> @if [ "$(MONITOR)" = "1" ]; then $(MAKE) --no-print-directory monitor; fi

monitor: ## Serial monitor of the plugged-in box (Ctrl+C leaves)
> @test -n "$(PORT)" || { echo "No board found. Plug the box in, or pass PORT=/dev/ttyUSBn"; exit 1; }
> -$(PIO) device monitor --port $(PORT) --baud 115200

ports: ## Which USB serial ports are present
> @ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "none"

build: config ## Compile all four box builds, upload nothing
> cd $(FIRMWARE) && $(PIO) run -e node_left -e node_middle -e node_right -e node_fourth

config:
> @if [ ! -f "$(CONFIG_LOCAL)" ]; then \
>   if [ -f "$(CONFIG_BACKUP)" ]; then cp "$(CONFIG_BACKUP)" "$(CONFIG_LOCAL)" && echo "== copied hotspot config to firmware/include/config.local.h"; \
>   else echo "firmware/include/config.local.h is missing (hotspot name and password, pins). Copy it from another checkout."; exit 1; fi; \
> fi

status: ## What would be flashed and run: commits, config, ports
> @echo "tracker: $$(git log -1 --format='%h %s') $$(git symbolic-ref -q --short HEAD || echo '(detached)')"
> @echo "game:    $$(git -C $(GAME) log -1 --format='%h %s') $$(git -C $(GAME) symbolic-ref -q --short HEAD || echo '(detached)')"
> @test -f "$(CONFIG_LOCAL)" && echo "config:  firmware/include/config.local.h present" || echo "config:  firmware/include/config.local.h MISSING (make config)"
> @grep -q 'ESP32-Battery' $(FIRMWARE)/src/main.cpp && echo "build:   has the battery soft access point" || echo "build:   plain tracker firmware"
> @echo "ports:   $$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | tr '\n' ' ')"

# ---- game and tracker ------------------------------------------------------

game: ## Game with the Godot view and the real boxes (latest UI and tracker)
> cd $(GAME) && $(GAME_PY) -m software.game.main --frontend godot

game-pygame: ## Game in its own Pygame window with the real boxes
> cd $(GAME) && $(GAME_PY) -m software.game.main

game-sim: ## Game with the Godot view and a simulated player (W/A/S/D), no boxes
> cd $(GAME) && $(GAME_PY) -m software.game.main --frontend godot --input swarm-sim

tracker: ## Tracker window alone, three boxes (config.prototype.json)
> python3 -m whack --tracker swarm --config config.prototype.json

tracker-pvp: ## Tracker window alone, four boxes and two zones (config.pvp.json)
> python3 -m whack --tracker swarm --config config.pvp.json --calibration calibration.pvp.json

tracker-sim: ## Tracker window with a simulated player, no boxes
> python3 -m whack --simulate

# ---- housekeeping ----------------------------------------------------------

test: test-tracker test-game ## Both test suites

test-tracker: ## Tracker tests
> python3 -m unittest discover -s tests 2>&1 | tail -3

test-game: ## Game tests (headless)
> cd $(GAME) && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy $(GAME_PY) -m unittest discover -s testing 2>&1 | tail -3

update: ## Fetch both repos; fast-forward whichever branch is checked out
> @for repo in "$(CURDIR)" "$(GAME)"; do \
>   echo "== $$repo"; git -C "$$repo" fetch -q --all --prune; \
>   if git -C "$$repo" symbolic-ref -q HEAD >/dev/null; then git -C "$$repo" pull --ff-only | tail -1; else echo "   detached HEAD at $$(git -C "$$repo" log -1 --format='%h'), fetched only"; fi; \
>   echo "   main is $$(git -C "$$repo" rev-list --count HEAD..origin/main) commits ahead of this checkout"; \
> done
