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
#
# Evidence for the test report: `make record LABEL=walk-3box` (or record-pvp,
# game-record) writes a timestamped CSV under results/field/, and
# `make metrics` summarises every CSV there (dot %, Hz, losses/min, reacquire s).
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
RESULTS       := $(CURDIR)/results/field
STAMP         := $(shell date +%Y%m%d-%H%M%S)
LABEL         ?= run
CSV           ?= $(wildcard $(RESULTS)/*.csv)

.DEFAULT_GOAL := help
.PHONY: help left middle right fourth upload monitor ports build config status \
        game game-pygame game-sim game-pvp3 tracker tracker-pvp tracker-pvp3 tracker-sim calibrate calibrate-pvp \
        record record-pvp game-record metrics \
        check test test-game test-tracker test-firmware compile smoke update

help: ## This list
> @echo "Boxes (your view):"
> @grep -E '^(left|middle|right|fourth|monitor|ports|build|status):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo "Game and tracker:"
> @grep -E '^(game|game-pygame|game-sim|game-pvp3|tracker|tracker-pvp|tracker-pvp3|tracker-sim|calibrate|calibrate-pvp):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo "Testing and evidence:"
> @grep -E '^(check|test|test-tracker|test-game|test-firmware|compile|smoke|record|record-pvp|game-record|metrics):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo "Housekeeping:"
> @grep -E '^(update):.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'
> @echo
> @echo "Box table (your view -> build): left=node_right  middle=node_middle  right=node_left  fourth=node_fourth"
> @echo "Evidence: make record LABEL=<what>  ->  results/field/<date>-<what>-tracker.csv  ->  make metrics"

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
> @echo "calib:   $$(ls calibration.local.json calibration.pvp.json 2>/dev/null | tr '\n' ' ')"
> @echo "csv:     $$(ls $(RESULTS)/*.csv 2>/dev/null | wc -l) recordings in results/field/"

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
tracker-pvp3: ## Tracker window alone, two zones on only THREE boxes (config.pvp-3box.json; right half one box)
> python3 -m whack --tracker swarm --config config.pvp-3box.json --calibration calibration.pvp-3box.local.json
game-pvp3: ## Game with the Godot view; two players on three boxes (no fourth box)
> cd $(GAME) && $(GAME_PY) -m software.game.main --frontend godot --pvp-field-config config/swarm-field-pvp-3box.json --pvp-calibration-file $(CURDIR)/calibration.game-pvp-3box.local.json
tracker-sim: ## Tracker window with a simulated player, no boxes
> python3 -m whack --simulate
calibrate: ## Three boxes: empty-field calibration at startup, writes calibration.local.json
> python3 -m whack --tracker swarm --config config.prototype.json --calibrate
calibrate-pvp: ## Four boxes: empty-field calibration at startup, writes calibration.pvp.json
> python3 -m whack --tracker swarm --config config.pvp.json --calibration calibration.pvp.json --calibrate

# ---- testing and evidence --------------------------------------------------
check: test test-firmware compile smoke ## Every automated gate: both suites, firmware parser test, compile, smoke runs
> @echo "== all automated checks passed"
test: test-tracker test-game ## Both Python test suites
test-tracker: ## Tracker tests (tests/)
> python3 -m unittest discover -s tests 2>&1 | grep -E '^(Ran|OK|FAILED|ERROR)'
test-game: ## Game tests (testing/, headless)
> cd $(GAME) && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy $(GAME_PY) -m unittest discover -s testing 2>&1 | grep -E '^(Ran|OK|FAILED|ERROR)'
test-firmware: ## Native firmware parser and calibration test (g++, no board)
> g++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include firmware/test/protocol_test.cpp -o /tmp/whack-firmware-protocol-test && /tmp/whack-firmware-protocol-test
compile: ## Byte-compile every Python file in both repos
> python3 -m compileall -q whack tools tests && cd $(GAME) && $(GAME_PY) -m compileall -q software testing && echo "compile OK"
smoke: ## Headless smoke runs: game one frame with the simulated tracker, tracker 5 s simulated
> cd $(GAME) && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy $(GAME_PY) -m software.game.main --smoke-test 2>&1 | grep -vE '^(pygame|Hello)' | tail -2; test $${PIPESTATUS[0]} -eq 0
> python3 -m whack --simulate --headless --seconds 5 2>&1 | tail -2
record: ## Tracker, three boxes, CSV to results/field/<date>-$(LABEL)-tracker.csv (LABEL=walk)
> @mkdir -p $(RESULTS)
> python3 -m whack --tracker swarm --config config.prototype.json --record $(RESULTS)/$(STAMP)-$(LABEL)-tracker.csv
record-pvp: ## Tracker, four boxes, CSV to results/field/<date>-$(LABEL)-pvp.csv
> @mkdir -p $(RESULTS)
> python3 -m whack --tracker swarm --config config.pvp.json --calibration calibration.pvp.json --record $(RESULTS)/$(STAMP)-$(LABEL)-pvp.csv
game-record: ## Game with the Godot view, per-frame CSV to results/field/<date>-$(LABEL)-game.csv
> @mkdir -p $(RESULTS)
> cd $(GAME) && $(GAME_PY) -m software.game.main --frontend godot --record $(RESULTS)/$(STAMP)-$(LABEL)-game.csv
metrics: ## Summarise tracker recordings (dot %, Hz, jitter, losses/min, reacquire s); CSV=file to pick one
> @test -n "$(CSV)" || { echo "No recordings in results/field/. Make one with: make record LABEL=walk"; exit 1; }
> python3 -m tools.session_metrics $(CSV)

# ---- housekeeping ----------------------------------------------------------
update: ## Fetch both repos; fast-forward whichever branch is checked out
> @for repo in "$(CURDIR)" "$(GAME)"; do \
>   echo "== $$repo"; git -C "$$repo" fetch -q --all --prune; \
>   if git -C "$$repo" symbolic-ref -q HEAD >/dev/null; then git -C "$$repo" pull --ff-only | tail -1; else echo "   detached HEAD at $$(git -C "$$repo" log -1 --format='%h'), fetched only"; fi; \
>   echo "   main is $$(git -C "$$repo" rev-list --count HEAD..origin/main) commits ahead of this checkout"; \
> done
