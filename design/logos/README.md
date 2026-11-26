# Logo options (concepts, 26 Nov 2026)

`logo-options.svg` holds five concepts. Open it in a browser.

1. Olive branch, framed: label draft A. Italic serif wordmark, line-drawn branch.
2. Modern, leaf accents: label draft B. Bold sans; the caron on Š and the accent on Ć are olive leaves.
3. Harvest seal: label draft C. Round stamp; the year changes each harvest.
4. Š monogram: arch (bottle shoulder) with Š; the caron is two leaves. For caps, favicon, wax seal, social avatar.
5. Old hollow tree: drawn from the family's old trees with hollow trunks.

These are concepts. The fonts fall back to Georgia/Arial where Playfair Display / Space Grotesk are not installed.
The chosen one gets redrawn with outlined text (paths) before it goes on labels.
No place name in any logo: a place name on the bottle can read as a regional origin claim.

## Generated tree logos (A to F)

`make_tree.py` grows an original olive tree (twisted trunk, tapered limbs, roots, individual leaves)
and writes `tree-A-...svg` to `tree-F-...svg` plus `preview.html` (open it in a browser).
Each version has a fixed seed, so a chosen tree can be regenerated exactly and then refined.
Run: `python design/logos/make_tree.py`

## Chosen: B, tree in a double ring (26 Nov 2026)

`make_final.py` builds the final set into `final/` and copies web versions to `static/img/`:

| File | Use |
|---|---|
| `final/mark.svg` | Detailed tree in ring. Labels, print, anything 80 px or larger |
| `final/mark-small.svg` | Simplified tree, thick ring. Favicon, header, caps, anything under 80 px |
| `final/mark-white.svg`, `mark-small-white.svg` | Reversed on dark green |
| `final/mark-black.svg` | One colour black (stamps, fax, engraving) |
| `final/logo-stacked.svg`, `logo-stacked-white.svg` | Mark with name underneath |
| `final/logo-horizontal.svg` | Mark with name to the right |
| `final/og-image.svg` | Social share image 1200 x 630 |
| `final/png/` | PNG exports (made with headless Chrome) |

The tree is seed 23; do not change its settings in `tree_full()` or the tree changes.
The name "ŠAKIĆ" is still live text (working title). Once the brand name is final, outline the
lettering with the licensed font (Playfair Display, OFL) before sending files to the printer.
