.PHONY: install migrate dev-backend dev-frontend test smoke rescore scan-now install-daily uninstall-daily daily-status

install:
	cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[dev]"
	cd backend && .venv/bin/python -m playwright install chromium
	cd frontend && npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

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
