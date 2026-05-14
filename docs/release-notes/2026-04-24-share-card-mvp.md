# Share Card MVP (Phase 1)

**Released:** 2026-04-24
**Scope:** Personal share card flow (匿名 landing → birth form → result card → save/share)
**Spec:** `docs/superpowers/specs/2026-04-24-share-card-mvp-design.md`
**Plan:** `docs/superpowers/plans/2026-04-24-share-card-mvp-implementation.md`

## What shipped

### Product
- New匿名 flow at `/` → `/card/:slug`; existing product preserved at `/app/*`
- 20-type × 10-十神 = 200-subtag system wired end-to-end
- html2canvas save-to-gallery (desktop download + iOS long-press overlay)
- WeChat JS-SDK share (朋友圈 + 好友会话), graceful fallback in non-WeChat browsers
- K-factor analytics (anonymous cookies, card_view / card_save / card_share / form_* events)

### Backend
- `POST /api/card` (public, no auth)
- `GET /api/card/:slug` (share-link preview, privacy-preserving)
- `POST /api/track` (anonymous events)
- `GET /api/admin/metrics` (admin-token gated)
- `GET /api/wx/jsapi-ticket` (WeChat signing)
- `card_shares` + `events` tables (Alembic 0003)

### Data
- `server/app/data/cards/types.json` — 20 types
- `server/app/data/cards/formations.json` — 10 十神, 20 suffixes (state-aware), 20 golden lines
- `server/app/data/cards/subtags.json` — 200 × 3 = 600 tag strings
- `server/app/data/cards/state_thresholds.json` — 5-档 → 绽放/蓄力 mapping
- `server/app/data/cards/illustrations/` — 20 generated 360×360 PNG illustrations
- `server/scripts/validate_cards_data.py` — data integrity gatekeeper

### Frontend
- `/` — LandingScreen + BirthForm + TimeSegmentPicker (6-segment time fallback)
- `/card/:slug` — Card + CardActions + UpgradeCTA (full mode) / preview mode
- `useCardStore` (zustand) — isolated from existing `useAppStore`

## What's next (Phase 2)

- Pair card (合盘) — blocked on PM/specs/04b copy finalization
- Anonymous → registered session card inheritance
- Paid deep reports unlock
- Operations dashboard UI

## Known limitations

- No SSR; WeChat is the only rich-preview share target
- WeChat features require 公众号 备案 + JS 安全域名 configuration (non-engineering, user推进)
- Domain `youshi.app` is a placeholder; replace before launch

## Required config

Set in `.env` for production:
- `WX_APP_ID`, `WX_APP_SECRET` — WeChat public account credentials
- `ADMIN_TOKEN` — non-empty string; required to access `/api/admin/metrics`
