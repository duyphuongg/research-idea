.PHONY: install migrate dev-backend dev-frontend test smoke rescore scan-now install-daily uninstall-daily daily-status up down

install:
	cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[dev]"
	cd backend && .venv/bin/python -m playwright install chromium
	cd frontend && npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

# --- Mở / tắt giao diện bằng 1 lệnh ---
up:
	@mkdir -p backend/data/logs
	@if lsof -ti tcp:8000 >/dev/null 2>&1; then echo "Backend đã chạy sẵn (cổng 8000)"; \
	else (cd backend && nohup .venv/bin/uvicorn --factory app.main:create_app --port 8000 > data/logs/backend.log 2>&1 < /dev/null &) ; echo "Đang bật backend…"; fi
	@if lsof -ti tcp:3000 >/dev/null 2>&1; then echo "Giao diện đã chạy sẵn (cổng 3000)"; \
	else cd frontend && if [ ! -f .next/BUILD_ID ] || [ -n "$$(find app components lib public next.config.ts package.json -newer .next/BUILD_ID 2>/dev/null | head -1)" ]; then \
	  echo "Đang build giao diện (chỉ khi code thay đổi)…"; npm run build > ../backend/data/logs/frontend-build.log 2>&1 || { echo "Build lỗi — xem backend/data/logs/frontend-build.log"; exit 1; }; fi; \
	  (nohup npm run start -- -p 3000 -H 0.0.0.0 > ../backend/data/logs/frontend.log 2>&1 < /dev/null &) ; echo "Đang bật giao diện…"; fi
	@for i in $$(seq 1 90); do curl -s -m 3 -o /dev/null localhost:3000 && curl -s -m 3 -o /dev/null localhost:8000/api/ping && break; sleep 1; done
	@open http://localhost:3000
	@echo "Giao diện: http://localhost:3000 — tắt bằng: make down (log: backend/data/logs/)"
	@TS=$$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale); \
	NAME=$$($$TS status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null); \
	if [ -n "$$NAME" ]; then echo "Từ điện thoại/máy khác (Tailscale): http://$$NAME:3000"; fi

down:
	-@lsof -ti tcp:8000 | xargs kill 2>/dev/null; lsof -ti tcp:3000 | xargs kill 2>/dev/null; echo "Đã tắt backend và giao diện."

dev-backend:
	cd backend && .venv/bin/uvicorn --factory app.main:create_app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q

smoke:
	cd backend && .venv/bin/python scripts/smoke.py

rescore:
	cd backend && .venv/bin/python scripts/rescore.py

# --- Quét tự động mỗi ngày (macOS launchd) ---
DAILY_LABEL := io.podtrendradar.daily-scan
DAILY_PLIST := $(HOME)/Library/LaunchAgents/$(DAILY_LABEL).plist
DAILY_HOUR ?= 8

scan-now:
	cd backend && .venv/bin/python scripts/daily_scan.py

install-daily:
	mkdir -p backend/data/logs $(HOME)/Library/LaunchAgents
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__HOUR__#$(DAILY_HOUR)#g" -e "s#__LABEL__#$(DAILY_LABEL)#g" \
		deploy/launchd/daily-scan.plist.template > $(DAILY_PLIST)
	-launchctl bootout gui/$$(id -u) $(DAILY_PLIST) 2>/dev/null
	launchctl bootstrap gui/$$(id -u) $(DAILY_PLIST)
	@echo "Đã cài: quét mỗi ngày lúc $(DAILY_HOUR):00 (giờ máy). Log: backend/data/logs/daily-scan.log"

uninstall-daily:
	-launchctl bootout gui/$$(id -u) $(DAILY_PLIST)
	rm -f $(DAILY_PLIST)
	@echo "Đã gỡ lịch quét hằng ngày."

daily-status:
	@launchctl print gui/$$(id -u)/$(DAILY_LABEL) 2>/dev/null | grep -E "state =|last exit code|runs =" || echo "Chưa cài (make install-daily)"
	@tail -n 25 backend/data/logs/daily-scan.log 2>/dev/null || true
