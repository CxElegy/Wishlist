# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Owner (the operator):** one person who follows a personal watchlist of games, anime, film and TV, sports, live shows, goods and phones. They check the page every day on a phone and a computer, vote 👍 / 👎, add watch items from the settings page, and add things they want to the wishlist (including by uploading a photo).
- **Public readers (confirmed 2026-10-15):** the site is public, and people who don't know the owner will see it. A first-time visitor has to be able to tell what the page is, how it's organised, and how new it is. (Assumption: they read on a phone just as often as on a computer.)

## Product Purpose

Every 2 hours it collects the latest news on the watch items from free RSS feeds and APIs, and lays it out with one fixed section per item. Urgent news (release-date announcements, pre-registration, test dates) goes out by Discord the same day; everything else goes into the weekly digest. Success means the watch items' news can be caught up on in one page, without missing anything or seeing duplicates.

## Positioning

- **AI doesn't go online:** scripts collect the information, and AI only edits what was collected (merges duplicates, writes Chinese headlines). Token use stays low and there are no made-up facts.
- **Only AI-edited stories go on a section (decided 2026-10-17):** newly collected entries the AI editor hasn't organised yet don't appear as stories; they wait in a collapsed 「整理待ち N 件」 list (original title + source) at the bottom of the section. The only exception is urgent news (`urgent_patterns`), which goes up at once as 重大. The background gate wakes the AI editor whenever there are waiting entries (at most every 2 hours).
- **Each item has its own fixed section:** each item keeps the same section in its own colour scheme, and only the news inside changes. It's not a news site's time-ordered feed. Sections (genres) stay in a fixed order; inside a genre, sub-categories and then items are ordered by their heat score, so the hottest come first (the left index uses the same order).
- **Fed by the wishlist:** the 「気になるかも？」 recommendations combine the wishlist's preference tags, the watched sections, and the user's 👍 votes.

## Operating Context

- GitHub Actions (collect and publish every 2 hours) → GitHub Pages (static HTML). A Claude scheduled task (AI editing) no longer runs on a clock (stopped 2026-10-17); the background gate (`scripts/gate.py`) wakes it after a collection leaves entries waiting (on by default for AI editing; the repository variable `GATE_FIRE=0` turns it off).
- Supabase stores votes, settings-page requests, photo uploads and the news archive. The page writes to it directly with the public key.
- Discord receives urgent notices and the weekly digest.
- Article bodies stay in their original languages (Japanese, Simplified Chinese, Traditional Chinese, Korean, English). AI headlines are written in Chinese.

## Capabilities and Constraints

- The page is a static HTML file that `scripts/render.py` generates whole. No server-side processing or build tools. Fonts come from Google Fonts.
- **Interface language is Japanese** (confirmed 2026-10-15): headings, buttons and explanatory text. Article contents are not translated.
- Images are hotlinked from the source site (no Referer is sent, and site access controls are not bypassed). If no image is available, the work's cover is used, then the source site's icon.
- **Content that will grow (confirmed 2026-10-15):** new genres, prices and sales, dates and events, video and galleries. Build reusable parts so they can be added without redesigning the page.
- Undecided: whether to support dark mode, and whether to add pages other than the wishlist and settings pages.

## Brand Commitments

- Name: **ウォッチリスト通信** (formerly 关注清单通信). The title is never split across lines.
- Each watch item's section uses colours taken from that work's cover (`scripts/theme.py`).

## Evidence on Hand

- Real data: `reports/` (each published issue), `inbox/` (collected entries), `state/recommend.json` (recommendation candidates), `wishlist.yaml`.
- Diagrams: `docs/design/*.png` (architecture, flow, etc.).
- Testimonials, user numbers and outside reviews don't exist. Don't invent them.

## Product Principles

1. **The section is the unit:** new information belongs to some section (a watch item or a genre). Don't add a new category that doesn't belong to any section.
2. **Don't show what can't be read:** for missing images, contrast failures or text that doesn't fit, show a substitute (cover → icon → text list) rather than an empty frame.
3. **Write the real reason:** recommendations and badges show the actual condition that matched. No reasons invented for show.
4. **Don't show the same thing twice:** don't repeat news already shown in a section in other places (such as recommendations).

## Accessibility & Inclusion

- WCAG AA: text 4.5:1, large text 3:1. On coloured backgrounds the colour adapts itself (`render._legible`).
- Functional text is 11px or larger; decorative English labels are 10px or larger.
- No horizontal scrolling at 320px width. The page stays readable without JavaScript (shows the first batch).
