import { describe, it, expect } from "vitest";
import { isTrivialResponse } from "@/lib/dashboard/topic-detector";

describe("isTrivialResponse", () => {
  it("identifies short acks as trivial", () => {
    expect(isTrivialResponse("ok")).toBe(true);
    expect(isTrivialResponse("thanks")).toBe(true);
    expect(isTrivialResponse("got it")).toBe(true);
    expect(isTrivialResponse("sure")).toBe(true);
    expect(isTrivialResponse("Done!")).toBe(true);
    expect(isTrivialResponse("lol")).toBe(true);
  });

  it("identifies substantive text as non-trivial", () => {
    expect(isTrivialResponse("Here are your contacts from the CRM")).toBe(false);
    expect(isTrivialResponse("Pretty damp and gray out there")).toBe(false);
  });

  it("identifies empty string as trivial", () => {
    expect(isTrivialResponse("")).toBe(true);
  });

  it("identifies emoji as trivial", () => {
    expect(isTrivialResponse("👍")).toBe(true);
    expect(isTrivialResponse("✅")).toBe(true);
  });

  it("identifies greetings as trivial", () => {
    expect(isTrivialResponse("hello")).toBe(true);
    expect(isTrivialResponse("hey")).toBe(true);
    expect(isTrivialResponse("hi")).toBe(true);
  });

  it("identifies polite closings as trivial", () => {
    expect(isTrivialResponse("no problem")).toBe(true);
    expect(isTrivialResponse("sounds good")).toBe(true);
    expect(isTrivialResponse("will do")).toBe(true);
    expect(isTrivialResponse("you're welcome")).toBe(true);
  });

  it("treats long text as non-trivial even if it starts with a trivial word", () => {
    expect(isTrivialResponse("ok so here is what I was thinking about the project")).toBe(false);
  });

  it("identifies whitespace-only string as trivial", () => {
    expect(isTrivialResponse("   ")).toBe(true);
    expect(isTrivialResponse("\n\t")).toBe(true);
  });

  it("identifies short acks with punctuation as trivial", () => {
    expect(isTrivialResponse("sure!")).toBe(true);
    expect(isTrivialResponse("yep.")).toBe(true);
    expect(isTrivialResponse("hm")).toBe(true);
  });

  it("identifies non-trivial mixed messages", () => {
    expect(isTrivialResponse("ok show me")).toBe(false);
    expect(isTrivialResponse("show me the prescriptions")).toBe(false);
    expect(isTrivialResponse("what's the weather")).toBe(false);
  });

  it("treats any text over 50 chars as non-trivial", () => {
    const longText = "a".repeat(51);
    expect(isTrivialResponse(longText)).toBe(false);
  });
});
