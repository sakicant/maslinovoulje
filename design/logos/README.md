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
