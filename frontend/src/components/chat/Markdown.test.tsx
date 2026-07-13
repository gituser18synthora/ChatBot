import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Markdown } from "./Markdown";

describe("Markdown (assistant message rendering)", () => {
  it("renders headings, emphasis, lists and blockquotes", () => {
    const { container } = render(
      <Markdown>{"## Title\n\n**bold** and *italic*\n\n- item 1\n- item 2\n\n> quoted\n\n---"}</Markdown>,
    );
    expect(container.querySelector("h2")?.textContent).toBe("Title");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("blockquote")).not.toBeNull();
    expect(container.querySelector("hr")).not.toBeNull();
  });

  it("renders GFM tables inside a horizontal-scroll wrapper", () => {
    const md = "| Product | Price |\n| --- | --- |\n| X100 | $10 |";
    const { container } = render(<Markdown>{md}</Markdown>);
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("overflow-x-auto");
    expect(container.querySelector("th")?.textContent).toBe("Product");
    expect(container.querySelector("td")?.textContent).toBe("X100");
  });

  it("syntax-highlights code blocks and offers a copy button", () => {
    const md = "```python\nprint('hi')\n```";
    const { container, getByLabelText } = render(<Markdown>{md}</Markdown>);
    const code = container.querySelector("pre code");
    expect(code?.className).toContain("hljs");
    expect(code?.querySelector(".hljs-string")).not.toBeNull();
    expect(getByLabelText("Copy code")).toBeTruthy();
  });

  it("renders inline code and math", () => {
    const { container } = render(<Markdown>{"Use `npm run dev` and $E = mc^2$"}</Markdown>);
    expect(container.querySelector("p > code")?.textContent).toBe("npm run dev");
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("keeps safe inline HTML but strips scripts and event handlers", () => {
    const md = 'Hello <b>world</b> <script>window.hacked = true</script> <img src="x" onerror="window.hacked=true" />';
    const { container } = render(<Markdown>{md}</Markdown>);
    expect(container.querySelector("b")?.textContent).toBe("world");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")?.getAttribute("onerror")).toBeNull();
    expect((window as any).hacked).toBeUndefined();
  });

  it("opens links in a new tab with rel protection", () => {
    const { container } = render(<Markdown>{"[docs](https://example.com)"}</Markdown>);
    const a = container.querySelector("a");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noopener");
  });
});
