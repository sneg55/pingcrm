import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageEditor } from "./message-editor";

describe("MessageEditor", () => {
  it("renders with empty message when no suggestion", () => {
    render(<MessageEditor />);
    const textarea = screen.getByPlaceholderText("Write a message...");
    expect(textarea).toHaveValue("");
  });

  it("renders with pre-filled message from suggestion", () => {
    render(
      <MessageEditor
        suggestionId="s1"
        initialMessage="Hey, how are you?"
        initialChannel="telegram"
      />
    );
    const textarea = screen.getByPlaceholderText("Write a message...");
    expect(textarea).toHaveValue("Hey, how are you?");
  });

  it("shows Regenerate button via title", () => {
    render(
      <MessageEditor
        suggestionId="s1"
        initialMessage="Hello"
        initialChannel="email"
      />
    );
    expect(screen.getByTitle("Regenerate message")).toBeInTheDocument();
  });

  it("shows Regenerate button even without suggestionId", () => {
    render(<MessageEditor contactId="c1" />);
    expect(screen.getByTitle("Regenerate message")).toBeInTheDocument();
  });

  it("renders all three channel icon buttons", () => {
    render(<MessageEditor />);
    expect(screen.getByTitle("Send via Email")).toBeInTheDocument();
    expect(screen.getByTitle("Send via Telegram")).toBeInTheDocument();
    expect(screen.getByTitle("Send via Twitter/X")).toBeInTheDocument();
  });

  it("disables channels passed in disabledChannels", () => {
    render(
      <MessageEditor
        disabledChannels={{ telegram: "No Telegram username" }}
      />
    );
    const telegramBtn = screen.getByTitle("No Telegram username");
    expect(telegramBtn).toBeDisabled();
  });

  it("calls onSend with message and channel", () => {
    const onSend = vi.fn();
    render(
      <MessageEditor
        initialMessage="Test message"
        initialChannel="telegram"
        onSend={onSend}
      />
    );
    fireEvent.click(screen.getByTitle("Send"));
    expect(onSend).toHaveBeenCalledWith("Test message", "telegram", undefined);
  });

  it("disables send button when message is empty", () => {
    render(<MessageEditor initialChannel="telegram" />);
    const sendBtn = screen.getByTitle("Send");
    expect(sendBtn).toBeDisabled();
  });

  it("send button is enabled for all channels when message exists", () => {
    render(<MessageEditor initialMessage="Hi" initialChannel="email" />);
    expect(screen.getByTitle("Send")).not.toBeDisabled();
  });

  it("shows character count when message has content", () => {
    render(
      <MessageEditor initialMessage="Hello" initialChannel="telegram" />
    );
    // Char count shown as "5/4096" in a single span
    expect(screen.getByText(/5\/4096/)).toBeInTheDocument();
  });

  it("selects initial channel with active styling", () => {
    render(
      <MessageEditor initialMessage="" initialChannel="twitter" />
    );
    // Twitter button should have active styling (bg-stone-100)
    const twitterBtn = screen.getByTitle("Send via Twitter/X");
    expect(twitterBtn.className).toContain("bg-stone-100");
  });

  it("disables send button while sending and re-enables after", async () => {
    let resolve: () => void;
    const onSend = vi.fn(() => new Promise<void>((r) => { resolve = r; }));
    render(
      <MessageEditor
        initialMessage="Hello"
        initialChannel="telegram"
        onSend={onSend}
      />
    );
    const sendBtn = screen.getByTitle("Send");
    expect(sendBtn).not.toBeDisabled();

    fireEvent.click(sendBtn);
    // While sending, button should be disabled
    await waitFor(() => {
      expect(sendBtn).toBeDisabled();
    });

    // Double-click should not call onSend again
    fireEvent.click(sendBtn);
    expect(onSend).toHaveBeenCalledTimes(1);

    // Resolve the promise — button re-enables
    resolve!();
    await waitFor(() => {
      expect(sendBtn).not.toBeDisabled();
    });
  });

  it("defaults to first available channel when initial is disabled", () => {
    render(
      <MessageEditor
        initialChannel="email"
        disabledChannels={{ email: "No email" }}
      />
    );
    // Should fall back to telegram (next available) — telegram button has active bg
    const telegramBtn = screen.getByTitle("Send via Telegram");
    expect(telegramBtn.className).toContain("bg-stone-100");
  });
});
