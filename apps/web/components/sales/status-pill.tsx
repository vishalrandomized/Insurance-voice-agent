import type { CallbackStatus } from "@insurance/contracts";
import styles from "./sales-dashboard.module.css";

export const statusLabels: Record<CallbackStatus, string> = {
  not_requested: "No callback",
  requested: "Callback requested",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function StatusPill({
  status,
  compact = false,
}: {
  status: CallbackStatus;
  compact?: boolean;
}) {
  return (
    <span
      className={`${styles.statusPill} ${styles[`status_${status}`]} ${
        compact ? styles.statusCompact : ""
      }`}
    >
      <span className={styles.statusDot} />
      {statusLabels[status]}
    </span>
  );
}
