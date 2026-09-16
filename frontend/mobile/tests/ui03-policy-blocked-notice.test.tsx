import { isValidElement, type ReactElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => ({
  Pressable: "Pressable",
  StyleSheet: { create: <T,>(styles: T) => styles },
  Text: "Text",
  View: "View",
}));

import { Ui03PolicyBlockedNotice } from "../components/family/ui03-policy-blocked-notice";

describe("UI-03 policy-blocked notice", () => {
  it("explains the protected state without pretending assessment is missing", () => {
    const notice = Ui03PolicyBlockedNotice({
      onReviewAssessment: vi.fn(),
      onRetry: vi.fn(),
    });
    const copy = textContent(notice);

    expect(copy).toContain("家庭的隐私与同意设置正在保护这份支持方向");
    expect(copy).toContain("这不是尚未测评");
    expect(copy).toContain("不会继续读取或提交");
    expect(copy).not.toContain("完成并提交一次家庭测评后");
  });

  it("offers working review and retry actions", () => {
    const onReviewAssessment = vi.fn();
    const onRetry = vi.fn();
    const notice = Ui03PolicyBlockedNotice({
      onReviewAssessment,
      onRetry,
    });
    const buttons = elementsByType(notice, "Pressable");

    expect(
      buttons.map((button) => elementProps(button).accessibilityLabel),
    ).toEqual(["返回测评与同意设置", "重新检查查看权限"]);
    elementProps(buttons[0]).onPress();
    elementProps(buttons[1]).onPress();
    expect(onReviewAssessment).toHaveBeenCalledOnce();
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

function textContent(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) return node.map(textContent).join("");
  if (!isValidElement(node)) return "";
  return textContent(elementProps(node).children);
}

function elementsByType(node: ReactNode, type: string): ReactElement[] {
  if (Array.isArray(node)) {
    return node.flatMap((child) => elementsByType(child, type));
  }
  if (!isValidElement(node)) return [];
  const matches = node.type === type ? [node] : [];
  return [...matches, ...elementsByType(elementProps(node).children, type)];
}

function elementProps(element: ReactElement): {
  accessibilityLabel?: string;
  children?: ReactNode;
  onPress: () => void;
} {
  return element.props as {
    accessibilityLabel?: string;
    children?: ReactNode;
    onPress: () => void;
  };
}
