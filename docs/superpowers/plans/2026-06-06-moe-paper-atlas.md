# Vision MoE Paper Atlas Plan

## Objective

Build a GitHub Pages-ready static site that collects CV-focused MoE, routing, gating, and expert-system papers from curated CV conference metadata plus conservative CV-only external expansion.

## Scope

- Keep CVPR/ICCV/ECCV as the core source through `choucisan/CVpaper`.
- Add non-CVPR/ICCV/ECCV CV papers through arXiv cs.CV and OpenAlex.
- Exclude generic LLM/NLP/non-CV MoE work.
- Organize the UI by year first, then venue.
- Provide search and filters for tier, year, venue, and source.

## Verification

- Regenerate JSON data.
- Validate JSON syntax.
- Serve the static site locally.
- Use Playwright to verify rendering, data loading, and filter interaction.
- Push to GitHub and enable GitHub Pages.
