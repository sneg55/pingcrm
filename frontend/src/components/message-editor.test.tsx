import { render, screen, fireEvent } from "@testing-library/react";
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

  it("shows Regenerate button when suggestionId is provided", () => {
    render(
      <MessageEditor
        suggestionId="s1"
        initialMessage="Hello"
        initialChannel="email"
      />
    );
    expect(screen.getByText("Regenerate")).toBeInTheDocument();
  });

  it("shows Regenerate button even without suggestionId", () => {
    render(<MessageEditor contactId="c1" />);
    expect(screen.getByText("Regenerate")).toBeInTheDocument();
  });

  it("renders all three channel buttons", () => {
    render(<MessageEditor />);
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Twitter/X")).toBeInTheDocument();
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
    fireEvent.click(screen.getByText("Send"));
    expect(onSend).toHaveBeenCalledWith("Test message", "telegram");
  });

  it("disables send button when message is empty", () => {
    render(<MessageEditor initialChannel="telegram" />);
    const sendBtn = screen.getByText("Send").closest("button")!;
    expect(sendBtn).toBeDisabled();
  });

  it("shows 'Open Email' when email channel is selected", () => {
    render(<MessageEditor initialMessage="Hi" initialChannel="email" />);
    expect(screen.getByText("Open Email")).toBeInTheDocument();
    expect(screen.queryByText("Send")).not.toBeInTheDocument();
  });

  it("shows 'Open Twitter' when twitter channel is selected", () => {
    render(<MessageEditor initialMessage="Hi" initialChannel="twitter" />);
    expect(screen.getByText("Open Twitter")).toBeInTheDocument();
    expect(screen.queryByText("Send")).not.toBeInTheDocument();
  });

  it("shows 'Send' when telegram channel is selected", () => {
    render(<MessageEditor initialMessage="Hi" initialChannel="telegram" />);
    expect(screen.getByText("Send")).toBeInTheDocument();
    expect(screen.queryByText("Open Email")).not.toBeInTheDocument();
  });

  it("shows character count", () => {
    render(
      <MessageEditor initialMessage="Hello" initialChannel="telegram" />
    );
    expect(screen.getByText("5/4096")).toBeInTheDocument();
  });

  it("selects initial channel when provided", () => {
    render(
      <MessageEditor initialMessage="" initialChannel="twitter" />
    );
    // Twitter/X button should have the selected styling (slate color)
    const twitterBtn = screen.getByText("Twitter/X").closest("button")!;
    expect(twitterBtn.className).toContain("text-slate-600");
  });

  it("defaults to first available channel when initial is disabled", () => {
    render(
      <MessageEditor
        initialChannel="email"
        disabledChannels={{ email: "No email" }}
      />
    );
    // Should fall back to telegram (next available)
    const telegramBtn = screen.getByText("Telegram").closest("button")!;
    expect(telegramBtn.className).toContain("text-sky-600");
  });
});
