import SavedDrawing from "./SavedDrawing";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-leaflet", () => ({
  Polygon: ({ children }: any) => (
    <section data-testid="area">{children}</section>
  ),
  Polyline: ({ children }: any) => (
    <section data-testid="line">{children}</section>
  ),
  Popup: ({ children }: any) => <div>{children}</div>,
  Tooltip: ({ children }: any) => <div role="tooltip">{children}</div>,
}));
const drawing = {
  id: "drawing",
  name: "ZONE",
  closed: true,
  points: [
    { lat: 42, lng: 42 },
    { lat: 43, lng: 43 },
    { lat: 44, lng: 42 },
  ],
};
beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
});

it("shows a named area and deletes it by UUID", async () => {
  const changed = jest.fn();
  window.addEventListener("saved-points-changed", changed);
  render(<SavedDrawing drawing={drawing} flightId="flight" />);
  expect(screen.getByTestId("area")).toBeInTheDocument();
  expect(screen.getByRole("tooltip")).toHaveTextContent("ZONE");
  fireEvent.click(screen.getByText("Delete drawing"));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/flight/drawings/drawing"),
    expect.objectContaining({ method: "DELETE" }),
  );
  window.removeEventListener("saved-points-changed", changed);
});

it("keeps the geometry and reports a rejected rename", async () => {
  (fetch as jest.Mock).mockResolvedValue({
    ok: false,
    json: async () => ({ detail: "No such drawing" }),
  });
  render(
    <SavedDrawing drawing={{ ...drawing, closed: false }} flightId="flight" />,
  );
  fireEvent.change(screen.getByLabelText("Drawing name"), {
    target: { value: "BRIDGE" },
  });
  fireEvent.click(screen.getByText("Rename"));
  expect(await screen.findByRole("alert")).toHaveTextContent("No such drawing");
  expect(screen.getByTestId("line")).toBeInTheDocument();
});
