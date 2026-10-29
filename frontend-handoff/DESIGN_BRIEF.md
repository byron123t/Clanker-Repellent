# Redesign the frontend

Improve the visual quality and usability of this read-only dashboard. You have freedom
to change its layout, typography, colors, charts, and frontend code in `web/`.
The supplied server and fixed sample responses let you work independently.

The user should be able to:

1. Compare projects' recorded file coverage and understand each percentage's scope.
2. Select a file and see where recorded snippets appear within it.
3. Preview, copy, and download a snippet or saved file version.
4. Distinguish current records, historical records, and pending snapshots.
5. Browse saved response samples and download their original bodies.

Use `python3 preview.py --open` to run the app. `UI_GUIDE.md` describes the data needed
for these views. `reference/` contains starting desktop and mobile screenshots.

## Design criteria

- Establish clear hierarchy, readable type, and deliberate spacing.
- Use chart marks and color to explain the data. Make selection and hover/focus states clear.
- Make both sparse projects and the large file inventory easy to navigate.
- Distinguish unknown percentages from zero and historical counts from current totals.
- Keep the synthetic-data label visible as users navigate.
- Support keyboard interaction, accessible labels, and reduced motion.
- Fit narrow mobile screens and wide desktop layouts, including long paths and previews.
- Provide understandable loading, empty, error, and selected states.

## Keep working

Preserve the supplied data interface, project/record selection, file search, explicit
content previews, exact downloads, and copy controls. Display HTML and code examples as
text. Label binary previews and truncated content. Keep runtime assets within the four
frontend files so the owner can reuse the result directly.

## Return

Deliver the updated `web/` files, desktop/mobile screenshots, and a short note describing
the improvements, checks performed, and any unresolved issues. Test the populated, empty,
and error scenarios. Backend integration is the owner's follow-up task.
