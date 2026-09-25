#!/usr/bin/env python3
"""Build a self-contained, offline HTML gallery from the collection manifest.

Run with Python 3.11+ from any directory. No network or third-party packages.
The page uses a restrained native-CSS photo portfolio (variance 5, motion 1,
density 3); photographic color and the real theme palettes carry the design.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path, PurePosixPath
import re
import tomllib
from urllib.parse import quote


THEMES = ("canopy", "lagoon", "ember", "dusk")
AUTHOR = "Yuval Kolodkin-Gal"
AUTHOR_URL = "https://github.com/yuvalkolodkingal"

CSS = r"""
:root { color-scheme: dark; --bg:#151719; --surface:#202326; --fg:#edeeeb; --muted:#b0b6b7; --line:#42484b; --accent:#d6decb; }
* { box-sizing:border-box; }
html { scroll-behavior:auto; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
a { color:inherit; text-underline-offset:.24em; text-decoration-thickness:1px; }
a:hover { color:var(--accent); }
button { font:inherit; cursor:pointer; }
button,a { -webkit-tap-highlight-color:transparent; }
:focus-visible { outline:2px solid var(--accent); outline-offset:5px; }
[hidden] { display:none !important; }
.wrap { width:min(1440px,calc(100% - 96px)); margin-inline:auto; }
.skip { position:fixed; top:12px; left:12px; padding:10px 16px; background:var(--fg); color:var(--bg); transform:translateY(-160%); z-index:2; }
.skip:focus { transform:none; }
header { min-height:76px; display:flex; align-items:center; justify-content:space-between; gap:24px; border-bottom:1px solid var(--line); }
.signature { text-decoration:none; font-size:14px; font-weight:600; }
nav { display:flex; gap:28px; font-size:14px; }
nav a { text-decoration:none; }
.intro { padding:58px 0 34px; }
h1 { font-weight:450; font-size:clamp(36px,4.5vw,64px); letter-spacing:-.055em; line-height:1.08; margin:0 0 18px; }
.intro p { color:var(--muted); max-width:680px; margin:0; font-size:17px; }
h2 { font-size:28px; letter-spacing:-.035em; line-height:1.25; font-weight:500; margin:0 0 12px; }
h3 { font-size:18px; font-weight:500; margin:0; }
p { margin:0; }
.featured { display:grid; grid-template-columns:1.55fr 1fr; gap:28px; align-items:start; }
.featured figure { margin:0; }
.featured figure:nth-child(2) { padding-top:72px; }
.photo-link { display:block; background:var(--surface); }
.photo-link img { display:block; width:100%; height:auto; aspect-ratio:16/9; object-fit:cover; }
.photo-link:hover img { opacity:.92; }
.featured figcaption { display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px 16px; padding-top:12px; font-size:14px; }
.meta { color:var(--muted); }
section { scroll-margin-top:28px; }
.themes { padding:76px 0 62px; }
.section-copy { max-width:700px; color:var(--muted); }
.palette-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:28px; margin-top:28px; }
.palette { padding-top:20px; border-top:1px solid var(--line); }
.palette h3 { margin-bottom:12px; }
.swatches { display:flex; height:36px; margin:0 0 12px; padding:0; list-style:none; }
.swatches li { flex:1; background:var(--color); border:1px solid rgb(255 255 255 / .08); }
.palette a { color:var(--muted); font-size:14px; }
.collection { padding:0 0 76px; }
.toolbar { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px 24px; margin:24px 0 32px; border-bottom:1px solid var(--line); padding-bottom:18px; }
.filters { display:flex; flex-wrap:wrap; gap:6px; }
.filters button { color:var(--muted); background:transparent; border:1px solid transparent; padding:8px 16px; }
.filters button:hover { color:var(--fg); border-color:var(--line); }
.filters button[aria-pressed="true"] { color:var(--bg); background:var(--accent); border-color:var(--accent); }
.count { color:var(--muted); font-size:14px; }
.photo-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:42px 28px; }
.photo { min-width:0; }
.photo-info { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:4px 18px; padding-top:14px; }
.photo-info .meta { font-size:13px; }
.description { color:var(--muted); font-size:14px; margin:7px 0 12px; }
.downloads { display:flex; flex-wrap:wrap; gap:8px 24px; font-size:14px; }
.downloads a { white-space:nowrap; }
.empty { padding:32px 0; color:var(--muted); }
footer { padding:28px 0 36px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; display:flex; flex-wrap:wrap; justify-content:space-between; gap:12px 28px; }
dialog { background:var(--bg); color:var(--fg); border:1px solid var(--line); width:min(1280px,calc(100% - 32px)); max-height:calc(100dvh - 32px); padding:20px; }
dialog::backdrop { background:rgb(7 9 10 / .92); }
.viewer-top { display:flex; justify-content:space-between; align-items:center; gap:20px; margin-bottom:16px; }
.viewer-top h2 { margin:0; font-size:20px; }
.plain-button { background:var(--surface); border:1px solid var(--line); color:var(--fg); padding:7px 14px; white-space:nowrap; }
.plain-button:hover { border-color:var(--accent); }
.plain-button:active { transform:translateY(1px); }
.viewer-image { width:100%; display:block; max-height:calc(100dvh - 230px); min-height:80px; object-fit:contain; background:var(--surface); }
.viewer-bottom { display:flex; flex-wrap:wrap; gap:20px; justify-content:space-between; align-items:center; padding-top:18px; }
.viewer-nav { display:flex; gap:8px; }
.viewer-description { font-size:14px; color:var(--muted); margin-top:10px; }
.viewer-error { padding:20px 0; color:var(--fg); }
body:has(dialog[open]) { overflow:hidden; }
@media (min-width:1700px) { .wrap { width:min(1600px,calc(100% - 120px)); } }
@media (max-width:900px) { .wrap { width:calc(100% - 48px); } .featured { gap:20px; } .featured figure:nth-child(2) { padding-top:36px; } .palette-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width:640px) {
  .wrap { width:calc(100% - 32px); }
  header { min-height:70px; gap:16px; }
  .signature { max-width:150px; line-height:1.3; }
  nav { gap:18px; font-size:13px; }
  .intro { padding:38px 0 28px; }
  .intro p { font-size:15px; }
  .featured,.photo-grid { grid-template-columns:1fr; }
  .featured { gap:26px; }
  .featured figure:nth-child(2) { padding-top:0; }
  .themes { padding:50px 0; }
  .palette-grid { gap:24px 20px; }
  .toolbar { align-items:flex-start; margin-top:20px; }
  .filters { gap:2px; }
  .filters button { padding:7px 10px; font-size:14px; }
  .photo-grid { gap:32px; }
  .collection { padding-bottom:50px; }
  .photo-info { align-items:start; }
  dialog { padding:14px; }
  .viewer-top { align-items:start; }
  .viewer-bottom { gap:16px; }
  .viewer-image { max-height:calc(100dvh - 320px); }
}
"""

SCRIPT = r"""
(() => {
  'use strict';
  const cards = [...document.querySelectorAll('.photo')];
  const filterButtons = [...document.querySelectorAll('[data-filter]')];
  const count = document.getElementById('photo-count');
  let activeTheme = 'all';
  filterButtons.forEach(button => button.addEventListener('click', () => {
    activeTheme = button.dataset.filter;
    let visible = 0;
    cards.forEach(card => {
      card.hidden = activeTheme !== 'all' && card.dataset.theme !== activeTheme;
      if (!card.hidden) visible++;
    });
    filterButtons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    count.textContent = `${visible} ${visible === 1 ? 'photograph' : 'photographs'}`;
    document.getElementById('empty').hidden = visible !== 0;
  }));
  document.getElementById('filters').hidden = false;

  const viewer = document.getElementById('viewer');
  if (typeof viewer.showModal !== 'function') return;
  const picture = document.getElementById('viewer-image');
  let currentSlug = '';
  let returnFocus = null;
  let featureMode = false;
  const imageError = document.getElementById('viewer-error');
  picture.addEventListener('error', () => { imageError.hidden = false; });
  picture.addEventListener('load', () => { imageError.hidden = true; });

  const show = slug => {
    const card = cards.find(item => item.dataset.slug === slug);
    if (!card) return;
    currentSlug = slug;
    imageError.hidden = true;
    picture.alt = card.querySelector('img').alt;
    picture.src = card.querySelector('[data-fullhd]').getAttribute('href');
    document.getElementById('viewer-title').textContent = card.querySelector('h3').textContent;
    document.getElementById('viewer-description').textContent = card.querySelector('.description').textContent;
    ['master','fullhd'].forEach(kind => {
      const original = card.querySelector(`[data-${kind}]`);
      const link = document.getElementById(`viewer-${kind}`);
      link.href = original.getAttribute('href');
      link.download = original.getAttribute('download');
    });
  };
  document.querySelectorAll('[data-open]').forEach(link => link.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    featureMode = Boolean(link.closest('.featured'));
    returnFocus = link;
    show(link.dataset.open);
    viewer.showModal();
  }));
  function step(direction) {
    const available = cards.filter(card => featureMode || !card.hidden);
    const index = available.findIndex(card => card.dataset.slug === currentSlug);
    if (available.length) show(available[(index + direction + available.length) % available.length].dataset.slug);
  }
  document.getElementById('close-viewer').addEventListener('click', () => viewer.close());
  document.getElementById('previous').addEventListener('click', () => step(-1));
  document.getElementById('next').addEventListener('click', () => step(1));
  viewer.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft') { event.preventDefault(); step(-1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); step(1); }
  });
  viewer.addEventListener('click', event => {
    if (event.target !== viewer) return;
    const box = viewer.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) viewer.close();
  });
  viewer.addEventListener('close', () => {
    picture.removeAttribute('src');
    if (returnFocus) returnFocus.focus();
  });
})();
"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def local_url(value: object) -> str:
    """Keep generated asset references relative and within the repository."""
    raw = str(value)
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or ":" in raw or "\\" in raw:
        raise ValueError(f"Expected a repository-relative path, got {raw!r}")
    return quote(raw, safe="/-._~")


def swatches(root: Path, theme: str) -> str:
    path = root / "themes" / theme / "colors.toml"
    if not path.is_file():
        return '<p class="meta">Palette coming soon.</p>'
    values = tomllib.loads(path.read_text(encoding="utf-8"))
    values = values.get("colors", values)
    keys = ("background", "foreground", "accent", "green", "yellow", "magenta")
    selected = []
    seen = set()
    for key in keys:
        color = str(values.get(key, ""))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color) or color.lower() in seen:
            continue
        seen.add(color.lower())
        label = f"{key}: {color}"
        selected.append(f'<li style="--color:{color}" title="{escape(label)}" aria-label="{escape(label)}"></li>')
    return '<ul class="swatches" aria-label="Theme colors">' + "".join(selected) + "</ul>"


def photo_link(photo: dict, *, eager: bool = False) -> str:
    title = escape(photo["title"])
    description = escape(photo.get("description") or photo["title"])
    slug = escape(photo["slug"])
    loading = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    return (
        f'<a class="photo-link" href="{local_url(photo["fullhd"])}" data-open="{slug}" aria-label="View {title}">'
        f'<img src="{local_url(photo["preview"])}" alt="{description}" width="1600" height="900" {loading} decoding="async"></a>'
    )


def build(root: Path) -> str:
    manifest = json.loads((root / "metadata" / "collection.json").read_text(encoding="utf-8"))
    photos = manifest["wallpapers"]
    if not photos:
        raise ValueError("The collection has no wallpapers")
    slugs = set()
    for photo in photos:
        if photo["slug"] in slugs:
            raise ValueError(f"Duplicate wallpaper slug: {photo['slug']}")
        slugs.add(photo["slug"])
        photo["theme"] = str(photo["theme"]).lower()
        if photo["theme"] not in THEMES:
            raise ValueError(f"Unknown theme: {photo['theme']}")
        for key in ("preview", "master", "fullhd"):
            local_url(photo[key])

    author = escape(manifest.get("author", AUTHOR))
    first = next((photo for photo in photos if photo.get("featured")), photos[0])
    second = next((photo for photo in photos if photo.get("featured") and photo is not first), None)
    if second is None:
        second = next((photo for photo in photos if photo["theme"] == "ember" and photo is not first), None)
    if second is None:
        second = next((photo for photo in photos if photo["theme"] != first["theme"]), None)
    if second is None and len(photos) > 1:
        second = next(photo for photo in photos if photo is not first)
    highlights = [first] + ([second] if second else [])
    featured = "\n".join(
        f'<figure>{photo_link(photo, eager=index == 0)}<figcaption><span>{escape(photo["title"])}</span>'
        f'<span class="meta">{escape(photo["theme"].title())}</span></figcaption></figure>'
        for index, photo in enumerate(highlights)
    )
    palettes = "\n".join(
        f'<article class="palette"><h3>{theme.title()}</h3>{swatches(root, theme)}'
        f'<a href="themes/{theme}/colors.toml" download="{theme}-colors.toml">Download palette</a></article>'
        for theme in THEMES
    )
    cards = []
    for photo in photos:
        slug = escape(photo["slug"])
        theme = escape(photo["theme"])
        width, height = int(photo["width"]), int(photo["height"])
        cards.append(
            f'<article class="photo" id="{slug}" data-slug="{slug}" data-theme="{theme}">'
            f'{photo_link(photo)}<div class="photo-info"><h3>{escape(photo["title"])}</h3>'
            f'<span class="meta">{theme.title()} · {width} × {height}</span></div>'
            f'<p class="description">{escape(photo.get("description", ""))}</p>'
            f'<div class="downloads"><a data-master href="{local_url(photo["master"])}" download="{slug}.jpg">Full resolution</a>'
            f'<a data-fullhd href="{local_url(photo["fullhd"])}" download="{slug}-1920x1080.jpg">1920 × 1080</a></div></article>'
        )
    filters = '<button type="button" data-filter="all" aria-pressed="true">All</button>' + "".join(
        f'<button type="button" data-filter="{theme}" aria-pressed="false">{theme.title()}</button>' for theme in THEMES
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="author" content="{author}">
<meta name="description" content="Original photographs by {author}, edited for desktop wallpapers, with four matching Hyprland themes.">
<title>Wallpapers by {author}</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip" href="#collection">Skip to photographs</a>
<div class="wrap">
<header><a class="signature" href="{AUTHOR_URL}">{author}</a><nav aria-label="Main"><a href="#collection">Photographs</a><a href="#themes">Themes</a></nav></header>
<main>
<div class="intro"><h1>Photographs for your desktop.</h1><p>Original photography by {author}, edited for the screen. Four matching Hyprland themes.</p></div>
<div class="featured" role="region" aria-label="Featured photographs">{featured}</div>
<section class="themes" id="themes" aria-labelledby="themes-title"><h2 id="themes-title">Color beyond the photograph.</h2>
<p class="section-copy">Four palettes carry the photographs into Hyprland. <a href="README.md#themes">Theme setup and installation</a>.</p>
<div class="palette-grid">{palettes}</div></section>
<section class="collection" id="collection" aria-labelledby="collection-title"><h2 id="collection-title">The collection</h2>
<div class="toolbar"><div class="filters" id="filters" role="group" aria-label="Filter photographs by theme" hidden>{filters}</div><p class="count" id="photo-count" role="status" aria-live="polite">{len(photos)} photographs</p></div>
<div class="photo-grid">{''.join(cards)}</div><p class="empty" id="empty" hidden>No photographs in this theme yet.</p></section>
</main>
<footer><p>All photographs © {author}. All rights reserved.</p><a href="README.md">Collection notes</a></footer>
</div>
<dialog id="viewer" aria-labelledby="viewer-title" aria-describedby="viewer-description">
<div class="viewer-top"><h2 id="viewer-title" aria-live="polite">Photograph</h2><button class="plain-button" id="close-viewer" type="button" autofocus>Close</button></div>
<img class="viewer-image" id="viewer-image" alt="">
<p class="viewer-error" id="viewer-error" role="status" hidden>This preview could not be loaded. Use the download links below to open the photograph.</p>
<p class="viewer-description" id="viewer-description"></p>
<div class="viewer-bottom"><div class="downloads"><a id="viewer-master" download>Full resolution</a><a id="viewer-fullhd" download>1920 × 1080</a></div>
<div class="viewer-nav"><button class="plain-button" id="previous" type="button" aria-label="Previous photograph">Previous</button><button class="plain-button" id="next" type="button" aria-label="Next photograph">Next</button></div></div>
</dialog>
<script>{SCRIPT}</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root")
    args = parser.parse_args()
    root = args.root.resolve()
    result = build(root)
    destination = root / "index.html"
    destination.write_text(result, encoding="utf-8")
    print(f"Built {destination}")


if __name__ == "__main__":
    main()
