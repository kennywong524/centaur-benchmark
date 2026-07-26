# CentaurBench AAAI-27 submission package

This package is prepared for anonymous double-blind review in the AAAI-27 main technical track.

## Build

Compile the main paper from this directory with PDFLaTeX and BibTeX:

```text
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Compile the separate technical supplement with PDFLaTeX:

```text
pdflatex supplement.tex
```

The main paper and supplement both use the supplied `aaai2027.sty` and `aaai2027.bst` files. Do not replace them with an older AAAI style package.

## Uploads

- Upload the compiled `main.pdf` as the anonymous main-paper PDF.
- Upload the compiled `supplement.pdf` separately as the technical supplement.
- Upload the completed AAAI-27 reproducibility checklist separately in the designated OpenReview field.
- Keep the `[submission]` option until the paper is accepted; it is the mode that suppresses author and affiliation metadata.

The appendix is intentionally compiled through `supplement.tex` rather than appended to `main.tex`, because AAAI-27 reserves pages beyond the seven pages of main content for references only.

## Final checks before upload

Verify the generated PDFs locally for US Letter size, embedded Type 1 or TrueType fonts, no Type 3 fonts, no page numbers or custom headers/footers, no hyperlinks or bookmarks, and no clipped or overflowing figures. Also verify the final main-paper page allocation against the current OpenReview validator.
