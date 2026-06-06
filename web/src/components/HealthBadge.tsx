import { useEffect, useState } from "react";
import { getHealth, getReady } from "../lib/api";
import type { Health } from "../lib/api";

export function HealthBadge() {
  const [health, setHealth] = useState<Health | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const h = await getHealth();
      if (alive) setHealth(h);
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const status = health?.status ?? "offline";
  const ok = status === "ok";
  const degraded = status === "degraded";

  const failedDeps = health?.dependencies
    ? Object.entries(health.dependencies)
        .filter(([, v]) => v !== "ok")
        .map(([k]) => k)
    : [];

  const handleClick = async () => {
    const ready = await getReady();
    if (ready) {
      setHealth((prev) =>
        prev
          ? { ...prev, status: ready.status, dependencies: { ...prev.dependencies, ...ready.dependencies } }
          : { status: ready.status, dependencies: ready.dependencies },
      );
    }
    setShowDetails(true);
    setTimeout(() => setShowDetails(false), 5000);
  };

  return (
    <button
      type="button"
      className={`health health-${ok ? "ok" : degraded ? "degraded" : "warn"}`}
      title={`Backend: ${status}${failedDeps.length > 0 ? ` — ${failedDeps.join(", ")} down` : ""}`}
      onClick={handleClick}
    >
      <span className="health-dot" aria-hidden="true" />
      {status}
      {showDetails && failedDeps.length > 0 && (
        <span className="health-details">{failedDeps.join(", ")} down</span>
      )}
    </button>
  );
}
