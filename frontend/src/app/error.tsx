"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[ErrorBoundary]", error);
  }, [error]);

  return (
    <div style={{ padding: 40, color: "#fff", fontFamily: "monospace" }}>
      <h2 style={{ color: "#f87171" }}>Page Error</h2>
      <pre style={{ whiteSpace: "pre-wrap", color: "#fbbf24", fontSize: 14 }}>
        {error.message}
      </pre>
      <pre style={{ whiteSpace: "pre-wrap", color: "#94a3b8", fontSize: 12, marginTop: 8 }}>
        {error.stack}
      </pre>
      <button
        onClick={reset}
        style={{
          marginTop: 16,
          padding: "8px 16px",
          background: "#3b82f6",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: "pointer",
        }}
      >
        Retry
      </button>
    </div>
  );
}
