import type { Intent } from "./types";

export const EXAMPLE_PROMPTS: {
  label: string;
  intent: Intent;
  text: string;
}[] = [
  {
    label: "IR — Explain",
    intent: "IR",
    text: "What is retrieval-augmented generation and how does it work?",
  },
  {
    label: "AE — Build",
    intent: "AE",
    text: "Build a demo / UI.",
  },
  {
    label: "IR — Compare",
    intent: "IR",
    text: "Compare REST vs GraphQL for a mobile backend.",
  },
  {
    label: "AE — Implement",
    intent: "AE",
    text: "Implement user authentication with JWT and refresh tokens.",
  },
];
