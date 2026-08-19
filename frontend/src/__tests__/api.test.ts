import { describe, it, expect, beforeEach } from "vitest";
import {
  parseSSEEvents,
  isLoggedIn,
  logout,
} from "../api";

describe("parseSSEEvents", () => {
  it("parses a single data event", () => {
    const text = 'data: {"type":"answer","content":"hello","is_final":true}\n\n';
    const events = parseSSEEvents(text);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({
      type: "answer",
      content: "hello",
      is_final: true,
    });
  });

  it("parses multiple data events", () => {
    const text = [
      'data: {"type":"sources","sources":[]}',
      'data: {"type":"answer","content":"hi","is_final":false}',
      'data: {"type":"answer","content":"","is_final":true}',
    ].join("\n\n");
    const events = parseSSEEvents(text);
    expect(events).toHaveLength(3);
    expect(events[0].type).toBe("sources");
    expect(events[1].type).toBe("answer");
    expect(events[2].is_final).toBe(true);
  });

  it("skips malformed JSON lines", () => {
    const text = [
      'data: {"type":"answer","content":"ok"}',
      "data: not-json",
      'data: {"type":"answer","content":"done"}',
    ].join("\n");
    const events = parseSSEEvents(text);
    expect(events).toHaveLength(2);
  });

  it("returns empty array for empty string", () => {
    expect(parseSSEEvents("")).toEqual([]);
  });

  it("ignores non-data lines", () => {
    const text = "event: ping\ndata: {\"type\":\"answer\"}\n\n";
    const events = parseSSEEvents(text);
    expect(events).toHaveLength(1);
  });
});

describe("token management", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("isLoggedIn returns false when no token", () => {
    expect(isLoggedIn()).toBe(false);
  });

  it("isLoggedIn returns true when token exists", () => {
    localStorage.setItem("token", "test-token");
    expect(isLoggedIn()).toBe(true);
  });

  it("logout removes token from localStorage", () => {
    localStorage.setItem("token", "test-token");
    logout();
    expect(isLoggedIn()).toBe(false);
    expect(localStorage.getItem("token")).toBeNull();
  });
});
