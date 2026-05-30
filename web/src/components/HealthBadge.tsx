import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";

export function HealthBadge() {
  const [status, setStatus] = useState<string>("…");

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const h = await getHealth();
      if (alive) setStatus(h ? h.status : "offline");
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const ok = status === "ok";
  return (
    <span className={`health health-${ok ? "ok" : "warn"}`} title={`Backend: ${status}`}>
      <span className="health-dot" aria-hidden="true" />
      {status}
    </span>
  );
}
