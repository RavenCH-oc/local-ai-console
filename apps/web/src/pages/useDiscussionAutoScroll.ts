import { useCallback, useEffect, useRef } from "react";
import type { UIEvent } from "react";

export interface ScrollMetrics {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
}

const DEFAULT_NEAR_BOTTOM_THRESHOLD = 96;

export function isNearBottom(
  { scrollHeight, scrollTop, clientHeight }: ScrollMetrics,
  threshold = DEFAULT_NEAR_BOTTOM_THRESHOLD,
): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold;
}

/** Keep streaming navigation scoped to the message pane, never the document. */
export function useDiscussionAutoScroll(
  reasoningContent: string | undefined,
  visibleContent: string | undefined,
  persistedMessageCount: number,
) {
  const messageListRef = useRef<HTMLDivElement>(null);
  const shouldAutoFollowRef = useRef(true);
  const frameReference = useRef<number | null>(null);

  const scheduleFollow = useCallback(() => {
    if (frameReference.current !== null || typeof window.requestAnimationFrame !== "function") {
      return;
    }
    frameReference.current = window.requestAnimationFrame(() => {
      frameReference.current = null;
      const messageList = messageListRef.current;
      if (messageList) {
        messageList.scrollTop = messageList.scrollHeight;
      }
    });
  }, []);

  const followLatestMessage = useCallback(() => {
    shouldAutoFollowRef.current = true;
    scheduleFollow();
  }, [scheduleFollow]);

  const handleMessageListScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    shouldAutoFollowRef.current = isNearBottom(event.currentTarget);
  }, []);

  useEffect(() => {
    if (shouldAutoFollowRef.current) {
      scheduleFollow();
    }
  }, [persistedMessageCount, reasoningContent, scheduleFollow, visibleContent]);

  useEffect(
    () => () => {
      if (frameReference.current !== null) {
        window.cancelAnimationFrame(frameReference.current);
      }
    },
    [],
  );

  return { followLatestMessage, handleMessageListScroll, messageListRef };
}
