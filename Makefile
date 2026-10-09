.PHONY: install migrate dev-backend dev-frontend test smoke rescore scan-now backup install-daily uninstall-daily daily-status install-autostart uninstall-autostart up down telegram-setup digest-now

install:
	cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[dev]"
	cd frontend && npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

# --- Mở / tắt giao diện bằng 1 lệnh ---
# cổng giao diện (3000 hay trùng app khác)
UI_PORT ?= 3737
# cổng backend API (chỉ nghe trong máy)
API_PORT ?= 8020
up:
	@mkdir -p backend/data/logs
	@if lsof -ti tcp:$(API_PORT) >/dev/null 2>&1; then echo "Backend đã chạy sẵn (cổng $(API_PORT))"; \
	else (cd backend && nohup .venv/bin/uvicorn --factory app.main:create_app --port $(API_PORT) > data/logs/backend.log 2>&1 < /dev/null &) ; echo "Đang bật backend…"; fi
	@if lsof -ti tcp:$(UI_PORT) >/dev/null 2>&1; then echo "Giao diện đã chạy sẵn (cổng $(UI_PORT))"; \
	else cd frontend && if [ ! -f .next/BUILD_ID ] || [ -n "$$(find app components lib public next.config.ts package.json -newer .next/BUILD_ID 2>/dev/null | head -1)" ]; then \
	  echo "Đang build giao diện (chỉ khi code thay đổi)…"; BACKEND_URL=http://127.0.0.1:$(API_PORT) npm run build > ../backend/data/logs/frontend-build.log 2>&1 || { echo "Build lỗi — xem backend/data/logs/frontend-build.log"; exit 1; }; fi; \
	  (BACKEND_URL=http://127.0.0.1:$(API_PORT) nohup npm run start -- -p $(UI_PORT) -H 0.0.0.0 > ../backend/data/logs/frontend.log 2>&1 < /dev/null &) ; echo "Đang bật giao diện…"; fi
	@for i in $$(seq 1 90); do curl -s -m 3 -o /dev/null localhost:$(UI_PORT) && curl -s -m 3 -o /dev/null localhost:$(API_PORT)/api/ping && break; sleep 1; done
	@[ -n "$(NO_OPEN)" ] || open http://localhost:$(UI_PORT)
	@echo "Giao diện: http://localhost:$(UI_PORT) — tắt bằng: make down (log: backend/data/logs/)"
	@TS=$$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale); \
	NAME=$$($$TS status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null); \
	if [ -n "$$NAME" ]; then echo "Từ điện thoại/máy khác (Tailscale): http://$$NAME:$(UI_PORT)"; fi

down:
	-@lsof -ti tcp:$(API_PORT) | xargs kill 2>/dev/null; lsof -ti tcp:$(UI_PORT) | xargs kill 2>/dev/null; \
	for i in $$(seq 1 20); do lsof -ti tcp:$(API_PORT) -sTCP:LISTEN >/dev/null 2>&1 || lsof -ti tcp:$(UI_PORT) -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 0.5; done; \
	echo "Đã tắt backend và giao diện."

dev-backend:
	cd backend && .venv/bin/uvicorn --factory app.main:create_app --reload --port $(API_PORT)

dev-frontend:
	cd frontend && BACKEND_URL=http://127.0.0.1:$(API_PORT) npm run dev -- -p $(UI_PORT)

test:
	cd backend && .venv/bin/pytest -q

smoke:
	cd backend && .venv/bin/python scripts/smoke.py

rescore:
	cd backend && .venv/bin/python scripts/rescore.py

# --- Quét tự động mỗi ngày (macOS launchd) ---
DAILY_LABEL := io.podtrendradar.daily-scan
DAILY_PLIST := $(HOME)/Library/LaunchAgents/$(DAILY_LABEL).plist
DAILY_HOURS ?= 8 20

scan-now:
	cd backend && .venv/bin/python scripts/daily_scan.py

backup:
	cd backend && .venv/bin/python scripts/daily_scan.py --backup-only

install-daily:
	mkdir -p backend/data/logs $(HOME)/Library/LaunchAgents
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__LABEL__#$(DAILY_LABEL)#g" deploy/launchd/daily-scan.plist.template \
		| awk -v hours="$(DAILY_HOURS)" '/__INTERVALS__/ { n = split(hours, h, " "); for (i = 1; i <= n; i++) \
			printf "    <dict><key>Hour</key><integer>%d</integer><key>Minute</key><integer>0</integer></dict>\n", h[i]; next } 1' \
		> $(DAILY_PLIST)
	plutil -lint $(DAILY_PLIST) >/dev/null
	-launchctl bootout gui/$$(id -u) $(DAILY_PLIST) 2>/dev/null
	launchctl bootstrap gui/$$(id -u) $(DAILY_PLIST)
	@echo "Đã cài: quét mỗi ngày lúc $(foreach h,$(DAILY_HOURS),$(h):00) (giờ máy). Log: backend/data/logs/daily-scan.log"

uninstall-daily:
	-launchctl bootout gui/$$(id -u) $(DAILY_PLIST)
	rm -f $(DAILY_PLIST)
	@echo "Đã gỡ lịch quét hằng ngày."

daily-status:
	@launchctl print gui/$$(id -u)/$(DAILY_LABEL) 2>/dev/null | grep -E "state =|last exit code|runs =" || echo "Chưa cài (make install-daily)"
	@tail -n 25 backend/data/logs/daily-scan.log 2>/dev/null || true

telegram-setup:
	cd backend && .venv/bin/python scripts/telegram_setup.py

# xem trước + gửi ngay tin tổng kết tuần (không ảnh hưởng lịch gửi thứ Hai)
digest-now:
	cd backend && .venv/bin/python scripts/digest_now.py

# --- Tự bật giao diện khi đăng nhập máy ---
APP_LABEL := io.podtrendradar.app
APP_PLIST := $(HOME)/Library/LaunchAgents/$(APP_LABEL).plist
NODE_BIN := $(patsubst %/,%,$(dir $(shell command -v node)))

install-autostart:
	@[ -n "$(NODE_BIN)" ] || { echo "Không tìm thấy node trong PATH"; exit 1; }
	mkdir -p backend/data/logs $(HOME)/Library/LaunchAgents
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__LABEL__#$(APP_LABEL)#g" -e "s#__NODE_BIN__#$(NODE_BIN)#g" \
		deploy/launchd/app.plist.template > $(APP_PLIST)
	plutil -lint $(APP_PLIST) >/dev/null
	-launchctl bootout gui/$$(id -u) $(APP_PLIST) 2>/dev/null
	launchctl bootstrap gui/$$(id -u) $(APP_PLIST)
	@echo "Đã cài: tự bật giao diện mỗi khi đăng nhập máy. Log: backend/data/logs/autostart.log"

uninstall-autostart:
	-launchctl bootout gui/$$(id -u) $(APP_PLIST)
	rm -f $(APP_PLIST)
	@echo "Đã gỡ tự bật giao diện."
