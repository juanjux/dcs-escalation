import { RootState } from "../app/store";
import { gameLoaded, gameUnloaded } from "./actions";
import { createSlice } from "@reduxjs/toolkit";
import { HighCommandMark } from "./_liberationApi";

interface HighCommandState {
  marks: HighCommandMark[];
}

const initialState: HighCommandState = {
  marks: [],
};

const highCommandSlice = createSlice({
  name: "highCommand",
  initialState: initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder.addCase(gameLoaded, (state, action) => {
      // A save loaded by a server without the High Command sends no marks.
      state.marks = action.payload?.high_command ?? [];
    });
    builder.addCase(gameUnloaded, (state) => {
      state.marks = [];
    });
  },
});

export const selectHighCommandMarks = (state: RootState) =>
  state.highCommand.marks;

export default highCommandSlice.reducer;
