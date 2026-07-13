import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocStatusBadge, RoleBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders processing status", () => {
    render(<DocStatusBadge status="processing" />);
    expect(screen.getByText(/processing/i)).toBeInTheDocument();
  });
  it("renders failed status", () => {
    render(<DocStatusBadge status="failed" />);
    expect(screen.getByText(/failed/i)).toBeInTheDocument();
  });
  it("renders the Super User label for super_admin", () => {
    render(<RoleBadge role="super_admin" />);
    expect(screen.getByText(/super user/i)).toBeInTheDocument();
  });
});
