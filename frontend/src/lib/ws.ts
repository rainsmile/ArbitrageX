import type { WsChannel, WsConnectionStatus } from "@/types";

// ============================================================
// Types
// ============================================================

export interface WsMessage<T = unknown> {
  channel: WsChannel;
  event: string;
  data: T;
  timestamp: string;
}

export type WsMessageHandler<T = unknown> = (message: WsMessage<T>) => void;
export type WsStatusHandler = (status: WsConnectionStatus) => void;

interface ChannelState {
  ws: WebSocket | null;
  status: WsConnectionStatus;
  retryCount: number;
  retryTimer: ReturnType<typeof setTimeout> | null;
  handlers: Set<WsMessageHandler>;
  statusHandlers: Set<WsStatusHandler>;
}

// ============================================================
// Configuration
// ============================================================

const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000;
const MAX_RETRIES = 20;
const HEARTBEAT_INTERVAL_MS = 30000;

// ============================================================
// WebSocket Manager (singleton)
// ============================================================

class WebSocketManager {
  private channels: Map<WsChannel, ChannelState> = new Map();
  private heartbeatTimers: Map<WsChannel, ReturnType<typeof setInterval>> =
    new Map();

  // ----------------------------------------------------------
  // Public API
  // ----------------------------------------------------------

  /**
   * Subscribe to a channel. Returns an unsubscribe function.
   */
  subscribe<T = unknown>(
    channel: WsChannel,
    handler: WsMessageHandler<T>
  ): () => void {
    const state = this.getOrCreateChannel(channel);
    state.handlers.add(handler as WsMessageHandler);

    // Auto-connect when first subscriber arrives
    if (state.handlers.size === 1 && state.status === "disconnected") {
      this.connect(channel);
    }

    return () => {
      state.handlers.delete(handler as WsMessageHandler);
      // Auto-disconnect when last subscriber leaves
      if (state.handlers.size === 0) {
        this.disconnect(channel);
      }
    };
  }

  /**
   * Subscribe to connection status changes for a channel.
   */
  onStatusChange(channel: WsChannel, handler: WsStatusHandler): () => void {
    const state = this.getOrCreateChannel(channel);
    state.statusHandlers.add(handler);
    // Immediately fire with current status
    handler(state.status);
    return () => {
      state.statusHandlers.delete(handler);
    };
  }

  /**
   * Get current connection status of a channel.
   */
  getStatus(channel: WsChannel): WsConnectionStatus {
    return this.channels.get(channel)?.status ?? "disconnected";
  }

  /**
   * Get all channel statuses.
   */
  getAllStatuses(): Record<WsChannel, WsConnectionStatus> {
    const allChannels: WsChannel[] = [
      "market",
      "opportunities",
      "executions",
      "alerts",
    ];
    const result = {} as Record<WsChannel, WsConnectionStatus>;
    for (const ch of allChannels) {
      result[ch] = this.getStatus(ch);
    }
    return result;
  }

  /**
   * Manually connect to a channel.
   */
  connect(channel: WsChannel): void {
    const state = this.getOrCreateChannel(channel);
    if (state.ws && state.status === "connected") return;

    this.setStatus(channel, "connecting");

    try {
      const ws = new WebSocket(`${WS_BASE_URL}/${channel}`);

      ws.onopen = () => {
        state.retryCount = 0;
        this.setStatus(channel, "connected");
        this.startHeartbeat(channel);
      };

      ws.onmessage = (event) => {
        try {
          const raw = JSON.parse(event.data);
          // Normalize backend format {type, data, id, timestamp}
          // to frontend WsMessage {channel, event, data, timestamp}
          const message: WsMessage = {
            channel,
            event: raw.type ?? raw.event ?? "",
            data: raw.data ?? raw,
            timestamp: raw.timestamp ?? new Date().toISOString(),
          };
          for (const handler of state.handlers) {
            try {
              handler(message);
            } catch (err) {
              console.error(
                `[WS] Handler error on ${channel}:`,
                err
              );
            }
          }
        } catch {
          console.warn(
            `[WS] Failed to parse message on ${channel}:`,
            event.data
          );
        }
      };

      ws.onerror = () => {
        console.warn(`[WS] Connection error on ${channel}, will retry`);
        this.setStatus(channel, "error");
      };

      ws.onclose = () => {
        this.stopHeartbeat(channel);
        state.ws = null;

        // Only reconnect if there are still subscribers
        if (state.handlers.size > 0) {
          this.scheduleReconnect(channel);
        } else {
          this.setStatus(channel, "disconnected");
        }
      };

      state.ws = ws;
    } catch (err) {
      console.warn(`[WS] Failed to create connection for ${channel}:`, err);
      this.setStatus(channel, "error");
      this.scheduleReconnect(channel);
    }
  }

  /**
   * Disconnect from a channel.
   */
  disconnect(channel: WsChannel): void {
    const state = this.channels.get(channel);
    if (!state) return;

    // Cancel pending retries
    if (state.retryTimer) {
      clearTimeout(state.retryTimer);
      state.retryTimer = null;
    }

    this.stopHeartbeat(channel);

    if (state.ws) {
      state.ws.onclose = null; // prevent reconnect logic
      state.ws.close();
      state.ws = null;
    }

    state.retryCount = 0;
    this.setStatus(channel, "disconnected");
  }

  /**
   * Disconnect all channels.
   */
  disconnectAll(): void {
    for (const channel of this.channels.keys()) {
      this.disconnect(channel);
    }
  }

  /**
   * Send a message on a channel (if connected).
   */
  send(channel: WsChannel, data: unknown): boolean {
    const state = this.channels.get(channel);
    if (!state?.ws || state.ws.readyState !== WebSocket.OPEN) return false;
    state.ws.send(JSON.stringify(data));
    return true;
  }

  // ----------------------------------------------------------
  // Internal helpers
  // ----------------------------------------------------------

  private getOrCreateChannel(channel: WsChannel): ChannelState {
    let state = this.channels.get(channel);
    if (!state) {
      state = {
        ws: null,
        status: "disconnected",
        retryCount: 0,
        retryTimer: null,
        handlers: new Set(),
        statusHandlers: new Set(),
      };
      this.channels.set(channel, state);
    }
    return state;
  }

  private setStatus(channel: WsChannel, status: WsConnectionStatus): void {
    const state = this.channels.get(channel);
    if (!state || state.status === status) return;
    state.status = status;
    for (const handler of state.statusHandlers) {
      try {
        handler(status);
      } catch (err) {
        console.error(`[WS] Status handler error on ${channel}:`, err);
      }
    }
  }

  private scheduleReconnect(channel: WsChannel): void {
    const state = this.channels.get(channel);
    if (!state) return;

    if (state.retryCount >= MAX_RETRIES) {
      console.warn(
        `[WS] Max retries (${MAX_RETRIES}) exceeded for ${channel}`
      );
      this.setStatus(channel, "error");
      return;
    }

    const delay = Math.min(
      INITIAL_RETRY_DELAY_MS * Math.pow(2, state.retryCount),
      MAX_RETRY_DELAY_MS
    );

    this.setStatus(channel, "reconnecting");
    state.retryCount++;

    console.log(
      `[WS] Reconnecting ${channel} in ${delay}ms (attempt ${state.retryCount})`
    );

    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      this.connect(channel);
    }, delay);
  }

  private startHeartbeat(channel: WsChannel): void {
    this.stopHeartbeat(channel);
    const timer = setInterval(() => {
      this.send(channel, { type: "ping", timestamp: new Date().toISOString() });
    }, HEARTBEAT_INTERVAL_MS);
    this.heartbeatTimers.set(channel, timer);
  }

  private stopHeartbeat(channel: WsChannel): void {
    const timer = this.heartbeatTimers.get(channel);
    if (timer) {
      clearInterval(timer);
      this.heartbeatTimers.delete(channel);
    }
  }
}

// ============================================================
// Singleton export
// ============================================================

export const wsManager = new WebSocketManager();
