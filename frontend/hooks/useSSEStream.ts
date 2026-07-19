/**
 * AegisFlow :: hooks/useSSEStream.ts
 * ───────────────────────────────────
 * Reactive hook that consumes a ReadableStream from a fetch() SSE response
 * and parses structured `data:` lines into typed SSEEvent objects.
 *
 * Uses the Fetch API's ReadableStream (not EventSource) so it works with
 * POST bodies (workflow/run) and custom HTTP headers.
 */

"use client";

import { useCallback, useRef } from "react";
import type { SSEEvent, SSEEventType } from "@/lib/types";

export type SSECallback = (event: SSEEvent) => void;

interface UseSSEStreamReturn {
  consume: (response: Response, onEvent: SSECallback) => Promise<void>;
  abort: () => void;
}

export function useSSEStream(): UseSSEStreamReturn {
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const consume = useCallback(
    async (response: Response, onEvent: SSECallback): Promise<void> => {
      if (!response.body) throw new Error("SSE response has no body");

      const controller = new AbortController();
      abortRef.current = controller;

      const reader = response.body
        .pipeThrough(new TextDecoderStream())
        .getReader();

      // SSE buffer: accumulate lines until double-newline boundary
      let buffer = "";
      let currentEvent = "";

      const parseBlock = (block: string) => {
        const lines = block.split("\n");
        let sseEventLine: SSEEventType | null = null;
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            sseEventLine = line.slice(6).trim() as SSEEventType;
            currentEvent = sseEventLine;
          } else if (line.startsWith("data:")) {
            dataStr = line.slice(5).trim();
          }
        }

        if (dataStr) {
          try {
            const parsed = JSON.parse(dataStr);

            // ── Backend compatibility ────────────────────────────────────
            // The AegisFlow backend embeds the event type INSIDE the JSON
            // body as the "event" key (format_sse_event() in main.py).
            // We prefer that over the SSE `event:` line when present.
            const resolvedEvent: SSEEventType =
              (parsed.event as SSEEventType) ??
              sseEventLine ??
              (currentEvent as SSEEventType) ??
              "NODE_TRANSITION";

            // Extract `data` sub-object if present, otherwise use the full payload.
            // The backend spreads everything at the top level, so we use it directly.
            const dataPayload = parsed.data ?? parsed;

            const sseEvt: SSEEvent = {
              event: resolvedEvent,
              data: dataPayload,
              timestamp: parsed.timestamp_utc ?? new Date().toISOString(),
            };
            onEvent(sseEvt);
          } catch {
            // Non-JSON data line — skip silently
          }
        }
      };

      try {
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += value;

          // Split on double-newline (SSE block boundary)
          const blocks = buffer.split(/\n\n/);
          buffer = blocks.pop() ?? "";

          for (const block of blocks) {
            if (block.trim()) parseBlock(block);
          }
        }
      } finally {
        reader.releaseLock();
      }
    },
    [],
  );

  return { consume, abort };
}
