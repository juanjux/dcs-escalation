import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Flight, Waypoint } from "../../api/liberationApi";
import { WaypointDialog } from "./WaypointMenu";

const mockEdit = jest.fn();
jest.mock("../../api/liberationApi", () => ({
  useEditWaypointMutation: () => [mockEdit],
}));

const target = {
  flight: { id: "flight" } as Flight,
  waypoint: {
    index: 1,
    name: "Hold",
    altitude_ft: 600,
    altitude_reference: "BARO",
    speed_kts: 250,
  } as Waypoint,
  at: { x: 10, y: 10 },
};

it("displays the server warning after accepting an unverified MSL edit", async () => {
  mockEdit.mockReturnValue({
    unwrap: () =>
      Promise.resolve({ warning: "Terrain elevation is unavailable." }),
  });
  const onError = jest.fn();
  const onClose = jest.fn();
  render(
    <WaypointDialog target={target} onClose={onClose} onError={onError} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() =>
    expect(onError).toHaveBeenCalledWith(
      "Warning: Terrain elevation is unavailable.",
    ),
  );
  expect(onClose).toHaveBeenCalled();
});

it("sends AGL as RADIO without changing the numeric altitude", async () => {
  mockEdit.mockReturnValue({
    unwrap: () => Promise.resolve({ warning: null }),
  });
  const onError = jest.fn();
  render(
    <WaypointDialog target={target} onClose={jest.fn()} onError={onError} />,
  );
  fireEvent.change(screen.getByLabelText("Reference"), {
    target: { value: "RADIO" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() =>
    expect(mockEdit).toHaveBeenLastCalledWith({
      flightId: "flight",
      waypointIdx: 1,
      waypointEdit: {
        name: "Hold",
        altitude_ft: 600,
        altitude_reference: "RADIO",
      },
    }),
  );
  expect(onError).not.toHaveBeenCalled();
});

it("displays the refusal when the edited MSL altitude is below terrain", async () => {
  mockEdit.mockReturnValue({
    unwrap: () =>
      Promise.reject({ data: { detail: "MSL altitude is below terrain." } }),
  });
  const onError = jest.fn();
  render(
    <WaypointDialog target={target} onClose={jest.fn()} onError={onError} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() =>
    expect(onError).toHaveBeenCalledWith("MSL altitude is below terrain."),
  );
});
