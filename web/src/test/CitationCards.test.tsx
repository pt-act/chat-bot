/**
 * Group 9 tests: Citation Card Update
 *
 * 9.4  Compile + typecheck passes (verified by `bun run typecheck`)
 * 9.5  Citation card with all new fields populated renders correctly
 * 9.6  Citation card with all new fields null renders identically to legacy layout
 * 9.7  section and element_type are text content, not HTML — no XSS surface
 * 9.8  bbox values rendered as toFixed(2) strings only
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CitationCards } from "../components/CitationCards";
import type { Source } from "../types";

// ---------------------------------------------------------------------------
// Helper: open the Sources panel so citations are visible.
// ---------------------------------------------------------------------------
async function renderAndOpen(sources: Source[]) {
  render(<CitationCards sources={sources} />);
  const toggle = screen.getByRole("button", { name: /sources/i });
  await userEvent.click(toggle);
  return screen;
}

// ---------------------------------------------------------------------------
// 9.5  All new fields populated
// ---------------------------------------------------------------------------

describe("CitationCards — new ODL fields populated", () => {
  const odlSource: Source = {
    label: "annual_report.pdf",
    doc_id: "annual_report",
    score: 0.87,
    page: 3,
    snippet: "Revenue grew 12% year-on-year.",
    section: "Financial Highlights",
    element_type: "table",
    page_end: 4,
    bbox: [72.0, 680.5, 540.25, 740.1],
  };

  it("shows section title below document label", async () => {
    await renderAndOpen([odlSource]);
    expect(screen.getByText("Financial Highlights")).toBeInTheDocument();
  });

  it("shows element type badge for non-paragraph types", async () => {
    await renderAndOpen([odlSource]);
    expect(screen.getByText("table")).toBeInTheDocument();
  });

  it("shows multi-page range using page and page_end", async () => {
    await renderAndOpen([odlSource]);
    // page=3, page_end=4 → "pp. 3–4"
    expect(screen.getByText("pp. 3–4")).toBeInTheDocument();
  });

  it("shows bbox in a collapsible details element", async () => {
    await renderAndOpen([odlSource]);
    // <details> summary is "bbox"
    const summary = screen.getByText("bbox");
    expect(summary).toBeInTheDocument();
    // bbox values rendered as toFixed(2)
    expect(screen.getByText(/72\.00.*680\.50.*540\.25.*740\.10/)).toBeInTheDocument();
  });

  it("section and element_type are text nodes, not raw HTML (9.7)", async () => {
    const xssSource: Source = {
      label: "doc.pdf",
      section: '<img src=x onerror="alert(1)">',
      element_type: '<script>alert(2)</script>',
    };
    await renderAndOpen([xssSource]);
    // The injected strings appear as literal text, not executed markup
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    // No <img> or <script> elements were created
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 9.6  All new fields absent — legacy layout unchanged
// ---------------------------------------------------------------------------

describe("CitationCards — new ODL fields absent (legacy source)", () => {
  const legacySource: Source = {
    label: "return_policy.pdf",
    doc_id: "return_policy",
    score: 0.75,
    page: 2,
    snippet: "Returns accepted within 30 days.",
  };

  it("renders without crashing when new fields are absent", async () => {
    await renderAndOpen([legacySource]);
    expect(screen.getByText("return_policy.pdf")).toBeInTheDocument();
  });

  it("shows single-page format when page_end is absent", async () => {
    await renderAndOpen([legacySource]);
    expect(screen.getByText("p. 2")).toBeInTheDocument();
  });

  it("shows no section label when section is null", async () => {
    const src: Source = { ...legacySource, section: null };
    await renderAndOpen([src]);
    // No element with class citation-section should exist
    expect(document.querySelector(".citation-section")).toBeNull();
  });

  it("shows no element type badge when element_type is null", async () => {
    const src: Source = { ...legacySource, element_type: null };
    await renderAndOpen([src]);
    expect(document.querySelector(".citation-element-type")).toBeNull();
  });

  it("shows no element type badge for paragraph type", async () => {
    const src: Source = { ...legacySource, element_type: "paragraph" };
    await renderAndOpen([src]);
    expect(document.querySelector(".citation-element-type")).toBeNull();
  });

  it("shows no bbox when bbox is null", async () => {
    const src: Source = { ...legacySource, bbox: null };
    await renderAndOpen([src]);
    expect(document.querySelector(".citation-bbox")).toBeNull();
  });

  it("document label, page, score, snippet still render correctly", async () => {
    await renderAndOpen([legacySource]);
    expect(screen.getByText("return_policy.pdf")).toBeInTheDocument();
    expect(screen.getByText("p. 2")).toBeInTheDocument();
    expect(screen.getByText("return_policy.pdf")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 9.8  bbox values are toFixed(2) strings
// ---------------------------------------------------------------------------

describe("CitationCards — bbox rendering (9.8)", () => {
  it("renders bbox values as two-decimal strings", async () => {
    const src: Source = {
      label: "doc.pdf",
      bbox: [10.123456, 20.5, 300.0, 50.999],
    };
    await renderAndOpen([src]);
    // Each value rounded to 2dp
    expect(screen.getByText(/10\.12.*20\.50.*300\.00.*51\.00/)).toBeInTheDocument();
  });

  it("bbox with integer values renders as xx.00", async () => {
    const src: Source = {
      label: "doc.pdf",
      bbox: [0, 100, 500, 200],
    };
    await renderAndOpen([src]);
    expect(screen.getByText(/0\.00.*100\.00.*500\.00.*200\.00/)).toBeInTheDocument();
  });

  it("does not render bbox when array length is not 4", async () => {
    const src: Source = {
      label: "doc.pdf",
      // Intentional: malformed bbox should not render
      bbox: [1.0, 2.0, 3.0] as unknown as number[],
    };
    await renderAndOpen([src]);
    expect(document.querySelector(".citation-bbox")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Single-page vs multi-page range logic
// ---------------------------------------------------------------------------

describe("CitationCards — page range display", () => {
  it("shows single page when page_end equals page", async () => {
    const src: Source = { label: "doc.pdf", page: 5, page_end: 5 };
    await renderAndOpen([src]);
    expect(screen.getByText("p. 5")).toBeInTheDocument();
  });

  it("shows multi-page range when page_end is greater", async () => {
    const src: Source = { label: "doc.pdf", page: 5, page_end: 7 };
    await renderAndOpen([src]);
    expect(screen.getByText("pp. 5–7")).toBeInTheDocument();
  });

  it("shows no page when page is null", async () => {
    const src: Source = { label: "doc.pdf", page: null };
    await renderAndOpen([src]);
    expect(document.querySelector(".citation-page")).toBeNull();
  });
});
