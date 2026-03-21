// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

const routeTitles: Record<string, string> = {
  "/workspace/dashboard": "Dashboard",
  "/workspace/chat": "Chat",
  "/workspace/agents": "Agents",
  "/workspace/workflows": "Workflows",
  "/workspace/knowledge": "Knowledge Base",
  "/workspace/factory": "Factory",
  "/workspace/health": "System Health",
  "/workspace/metrics": "Metrics",
  "/workspace/plugins": "Plugins",
  "/workspace/settings": "Settings",
  "/auth": "Sign In",
};

const RouteAnnouncer = () => {
  const location = useLocation();
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    const path = location.pathname;
    const title = routeTitles[path]
      || Object.entries(routeTitles).find(([key]) => path.startsWith(key + "/"))?.[1]
      || "Page";

    setAnnouncement(`Navigated to ${title}`);
  }, [location.pathname]);

  return (
    <div
      aria-live="polite"
      role="status"
      className="sr-only"
    >
      {announcement}
    </div>
  );
};

export default RouteAnnouncer;
