"use client";

import styles from "../../components/sales/sales-dashboard.module.css";

export default function SalesError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className={styles.errorPage}>
      <p className={styles.eyebrow}>Advisor console</p>
      <h1>We could not open the lead desk.</h1>
      <p>Refresh the console or try again in a moment.</p>
      <button className={styles.primaryButton} onClick={reset} type="button">
        Try again
      </button>
    </main>
  );
}
