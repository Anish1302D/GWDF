import React from "react";
import { ShieldCheck, AlertTriangle, OctagonAlert, HelpCircle } from "lucide-react";

const RISK_META = {
  Safe: {
    className: "badge-safe",
    Icon: ShieldCheck,
  },
  Watch: {
    className: "badge-watch",
    Icon: AlertTriangle,
  },
  Critical: {
    className: "badge-critical",
    Icon: OctagonAlert,
  },
  "Insufficient Data": {
    className: "badge-insufficient",
    Icon: HelpCircle,
  },
};

export default function RiskBadge({ riskClass, label, size = "md" }) {
  const meta = RISK_META[riskClass] || RISK_META["Insufficient Data"];
  const { Icon } = meta;
  return (
    <span className={`risk-badge ${meta.className} risk-badge-${size}`}>
      <Icon size={size === "lg" ? 18 : 14} aria-hidden="true" />
      <span>{label || riskClass}</span>
    </span>
  );
}
