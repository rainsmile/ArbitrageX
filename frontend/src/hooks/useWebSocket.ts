"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { wsManager, type WsMessage, type WsMessageHandler } from "@/lib/ws";
import type { WsChannel, WsConnectionStatus } from "@/types";
import { useSystemStore } from "@/store";

/**
 * Subscribe to a WebSocket channel with auto-connect / disconnect lifecycle.
 *
 * @param channel  The channel to subscribe to.
 * @param handler  Callback fired for every incoming message.
 * @param options  Optional configuration.
 */
export function useWebSocket<T = unknown>(
  channel: WsChannel,
  handler: WsMessageHandler<T>,
  options?: {
    /** Set to false to temporarily pause the subscription. Default: true */
    enabled?: boolean;
  }
) {
  const { enabled = true } = options ?? {};
  const [status, setStatus] = useState<WsConnectionStatus>(
    wsManager.getStatus(channel)
  );
  const [lastEvent, setLastEvent] = useState<WsMessage<T> | null>(null);
  const updateWsStatus = useSystemStore((s) => s.updateWsStatus);

  // Keep a stable ref for the handler so callers don't need to memoize
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const stableHandler = useCallback((msg: WsMessage<T>) => {
    setLastEvent(msg);
    handlerRef.current(msg);
  }, []);

  // Subscribe / unsubscribe based on `enabled`
  useEffect(() => {
    if (!enabled) return;

    const unsub = wsManager.subscribe<T>(channel, stableHandler);
    return unsub;
  }, [channel, enabled, stableHandler]);

  // Track connection status and sync to system store
  useEffect(() => {
    if (!enabled) {
      setStatus("disconnected");
      return;
    }

    const unsub = wsManager.onStatusChange(channel, (newStatus) => {
      setStatus(newStatus);
      updateWsStatus(channel, newStatus === "connected");
    });
    return unsub;
  }, [channel, enabled, updateWsStatus]);

  /** Imperatively send a message on the channel */
  const send = useCallback(
    (data: unknown) => wsManager.send(channel, data),
    [channel]
  );

  return { status, send, lastEvent };
}

/**
 * Convenience hook that subscribes to the "market" channel and
 * dispatches incoming tickers / orderbooks to the market store.
 */
export function useMarketStream(options?: { enabled?: boolean }) {
  const { enabled = true } = options ?? {};

  const { status, lastEvent } = useWebSocket(
    "market",
    (msg) => {
      // Dynamically import store to avoid circular deps
      const { useMarketStore } = require("@/store");
      const store = useMarketStore.getState();

      switch (msg.event) {
        case "ticker":
          store.setTicker(
            `${(msg.data as { exchange: string }).exchange}:${(msg.data as { symbol: string }).symbol}`,
            msg.data as never
          );
          break;
        case "orderbook":
          store.setOrderbook(
            `${(msg.data as { exchange: string }).exchange}:${(msg.data as { symbol: string }).symbol}`,
            msg.data as never
          );
          break;
        case "spread":
          // spreads arrive individually; batch them in store
          break;
      }
    },
    { enabled }
  );

  return { status, lastEvent };
}

/**
 * Subscribe to the "opportunities" channel and push to the market store.
 */
export function useOpportunityStream(options?: { enabled?: boolean }) {
  const { enabled = true } = options ?? {};

  const { status, lastEvent } = useWebSocket(
    "opportunities",
    (msg) => {
      const { useMarketStore } = require("@/store");
      const store = useMarketStore.getState();

      if (msg.event === "opportunity") {
        store.addOpportunity(msg.data as never);
      }
    },
    { enabled }
  );

  return { status, lastEvent };
}

/**
 * Subscribe to the "executions" channel and push to the execution store.
 */
export function useExecutionStream(options?: { enabled?: boolean }) {
  const { enabled = true } = options ?? {};

  const { status, lastEvent } = useWebSocket(
    "executions",
    (msg) => {
      const { useExecutionStore } = require("@/store");
      const store = useExecutionStore.getState();

      switch (msg.event) {
        case "execution_started":
          store.addExecution(msg.data as never);
          break;
        case "execution_updated":
        case "execution_completed":
        case "execution_failed":
          store.updateExecution(msg.data as never);
          break;
      }
    },
    { enabled }
  );

  return { status, lastEvent };
}

/**
 * Subscribe to the "alerts" channel and push to the alert store.
 */
export function useAlertStream(options?: { enabled?: boolean }) {
  const { enabled = true } = options ?? {};

  const { status, lastEvent } = useWebSocket(
    "alerts",
    (msg) => {
      const { useAlertStore } = require("@/store");
      const store = useAlertStore.getState();

      if (msg.event === "alert") {
        store.addAlert(msg.data as never);
      }
    },
    { enabled }
  );

  return { status, lastEvent };
}
