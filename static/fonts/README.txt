Self-hosted fonts, both SIL Open Font License 1.1 (licence texts in this folder).

  PlayfairDisplay.woff2          variable 400-900, roman
  PlayfairDisplay-Italic.woff2   variable 400-900, italic
  Inter.woff2                    variable 100-900 (+ optical size)

Source: github.com/google/fonts (ofl/playfairdisplay, ofl/inter), downloaded 26 Nov 2026.
Subset to Basic Latin, Latin-1, Latin Extended-A (Croatian Š Ć Č Ž Đ, German umlauts),
punctuation and the euro sign, then converted to woff2 with fontTools:

  python -m fontTools.subset FONT.ttf --unicodes="U+0000-00FF,U+0100-017F,U+0131,U+0152-0153,U+02C6-02DA,U+02DC,U+2000-206F,U+20AC,U+2116,U+2122,U+2190-2193,U+2212" --layout-features='*' --flavor=woff2 --output-file=FONT.woff2

Adding a language with other letters (Polish, Czech are fine; Greek, Cyrillic are not) needs a new subset.
